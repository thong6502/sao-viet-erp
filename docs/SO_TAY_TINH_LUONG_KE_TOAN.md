# SỔ TAY TÍNH LƯƠNG
## NHÀ MÁY IN SAO VIỆT NHẬT — Bản dùng cho kế toán tiền lương và nhân sự

> **Đọc dòng này trước khi làm bất cứ việc gì.**
>
> Trên màn **Lương → Bảng lương tháng** có **hai thao tác ra tiền, và chúng KHÁC NHAU**:
>
> **(1) Bấm nút “↻ Tính lại”** (lần đầu trong tháng nút này hiện chữ “Khởi tạo bảng lương”) — chạy lại **toàn bộ** chuỗi tính từ đầu: công → mức nền → phụ cấp → tăng ca → bảo hiểm → thuế → phạt → thực nhận.
>
> **(2) Mở cửa sổ “Sửa lương”, sửa một ô rồi bấm “Lưu”** — **KHÔNG** chạy lại chuỗi trên. Nó lấy lại các số **đã lưu sẵn trên dòng đó** rồi chỉ tính lại đoạn cuối: thuế → phạt → thực nhận.
>
> Hai đường này **đáng lẽ phải ra cùng một số**. Hiện có một số trường hợp chúng **ra hai số khác nhau** — liệt kê hết ở **Phần 14**.
>
> **Quy tắc sống còn: sau khi sửa một ô, ĐỪNG tin ngay số vừa hiện. Bấm “↻ Tính lại” rồi mới đọc số.**

> **BA VIỆC ĐANG HỎNG TRÊN MÀN HÌNH — phải báo bộ phận phần mềm mở lại, trong lúc chờ thì làm tay:**
>
> 1. **Ô chọn “Cách tính thuế TNCN”** và **ô tích “Áp dụng giảm trừ bản thân”** hiện **không còn trên màn hình** (tắt hiển thị từ 03/08/2026). ⇒ **Không đổi được cách tính thuế, không bỏ tích giảm trừ bản thân cho bất kỳ ai.** Hậu quả và cách xử lý tay: **mục 9.2**.
> 2. Trên **phiếu lương** (cả bản in của nhân sự lẫn màn “Phiếu lương của tôi”), hai ô **“Thu nhập tính thuế TNCN”** và **“Thu nhập miễn thuế”** đang bị ẩn. Tiền **không mất**, chỉ là không nhìn thấy — **mục 9.1**.
> 3. **Cột “Khoán”** trên bảng lương luôn bằng 0 vì **phần khai sản lượng chưa dùng được** — **mục 6.1**. Tổ nào đang bật công tắc “Lương khoán / sản lượng” là **đang bị cắt tăng ca mà không có khoán bù** — **mục 6.5**.

---

## MỤC LỤC

| Phần | Nội dung |
|---|---|
| 0 | Bảy nguyên tắc bất di bất dịch |
| 1 | Thứ tự tính một dòng lương |
| 2 | Công: công chuẩn · công thực · ngày “Nghỉ 1×” · công có đơn · công phép |
| 3 | Mức nền tháng & hệ số thử việc |
| 4 | Lương theo công · Chuyên cần · Phụ cấp · Thưởng · Hoa hồng |
| 5 | Tăng ca · Cơm ca · Phụ cấp ca đêm |
| 6 | Lương khoán |
| 7 | TỔNG THU — liệt kê đầy đủ |
| 8 | BHXH · BHYT · BHTN · Đoàn phí công đoàn |
| 9 | Thuế thu nhập cá nhân |
| 10 | Phạt kỷ luật & trần khấu trừ 30% |
| 11 | Tạm ứng · Lương đợt 1 · Khoản trừ danh mục · Thực nhận |
| 12 | **Hai ví dụ số chạy trọn vẹn** |
| 13 | **Những chỗ hệ thống làm khác cách tính tay** |
| 14 | Chỗ hai đường tính ra hai số — đừng tin số vừa hiện |
| 15 | **Việc phải kiểm trước khi chốt bảng lương · Hai file Excel xuất ra** |
| 16 | Bảng tra: tham số khai ở màn nào |
| Phụ lục A | Những cột dễ nhầm nhất trên phiếu lương |
| Phụ lục B | Ô khai bao nhiêu cũng không ra tiền |
| Phụ lục C | Việc hệ thống CHƯA làm — phải tính tay |

---

# 0. BẢY NGUYÊN TẮC BẤT DI BẤT DỊCH

1. **Mẫu số chia lương luôn là CÔNG CHUẨN của tháng**, không bao giờ là công thực đi làm. Công chuẩn thay đổi theo lịch từng tháng — tháng 2 có thể 24, tháng khác 27.
2. **Làm dôi công KHÔNG ra thêm tiền ở cột “Lương công”.** Phần dôi chỉ được trả qua phần cộng thêm ngày lễ / ngày nghỉ tuần, và phần đó nằm trong **cột “Tăng ca”**.
3. **Lương khoán là CỘNG THÊM**, không thay thế lương theo công.
4. **Mức đóng bảo hiểm bám ô “Lương cơ bản (đóng BH)”**, không bám tổng mức nền, không chia theo công.
5. **Tiền tăng ca + phụ cấp ca đêm + cơm ca được miễn thuế thu nhập cá nhân toàn bộ**, không có trần.
6. **Trần khấu trừ 30% chỉ kẹp rổ kỷ luật gồm ĐÚNG 6 khoản**: Giảm trừ khác · Đi trễ / nghỉ không phép · Điện thoại vượt trội · Phạt biên bản · Đồng phục / phạt 5S · Trừ lỗi hàng khoán. Bảo hiểm, thuế, đoàn phí, tạm ứng, lương đợt 1, khoản trừ danh mục **nằm ngoài trần** — trừ hết, không kẹp.
7. **Có hai lần chặn sàn 0**: một ở tổng thu sau phạt, một ở thực nhận. Tiền thiếu **biến mất**, hệ thống **không ghi nợ**, **không chuyển sang kỳ sau**.

---

# 1. THỨ TỰ TÍNH MỘT DÒNG LƯƠNG

Khi bấm **“↻ Tính lại”**, hệ thống chạy đúng thứ tự này:

| Bước | Việc làm |
|---|---|
| 1 | Tính **công chuẩn** cho cả kỳ theo màn **Chấm công → Lịch & Ngày lễ**. Kỳ lương đã chốt hoặc đã chi ⇒ chặn, không cho tính lại |
| 2 | Nạp dữ liệu chung: ngày trả lương lấy là **ngày cuối tháng**; bảng chấm công (đọc bản đã chốt nếu kỳ công đã chốt); bảng ca; phiếu tạm ứng / lương đợt 1 **đã duyệt**; mức lương đang hiệu lực; biểu thuế; bảng bậc phạt đi trễ; danh sách tổ làm khoán |
| 3 | Với từng nhân viên: xác định **trạng thái và phòng/tổ TẠI KỲ ĐÓ**; bỏ người đã nghỉ việc mà không còn công, không còn khoán, không còn dòng lương; **giữ nguyên các ô nhân sự đã gõ tay**; tính lại phạt đi trễ nếu ô đó chưa khoá tay |
| 4 | Ra **mức nền tháng** → nhân **hệ số thử việc** |
| 5 | Ra **đơn giá ngày** → **lương theo công** (công đi làm lấp trần trước, công phép lấy phần dư) |
| 6 | **Chuyên cần** trừ dần theo bậc |
| 7 | **Phụ cấp**: phụ cấp khác + thâm niên + khoản danh mục gán ở hồ sơ; tách riêng khoản phát sinh của kỳ, khoản trừ, khoản miễn thuế |
| 8 | **Tăng ca** + phần cộng thêm ngày lễ / ngày nghỉ tuần + tiền ngày “Nghỉ 1×” |
| 9 | **Cơm ca + phụ cấp ca** theo ca thực làm → **phụ cấp ca đêm theo giờ** |
| 10 | Thưởng chi tiết + lương ngày phép + trả đồng phục + điều chỉnh lương → ra **TỔNG THU (trước phạt)** |
| 11 | Đếm ngày nghỉ không lương → **bảo hiểm (4 nhánh)** → **đoàn phí công đoàn** |
| 12 | Làm tròn tổng thu trước phạt và tiền bảo hiểm → **tính thuế thu nhập cá nhân** |
| 13 | Áp **trần phạt 30%** → tổng thu sau phạt |
| 14 | Giữ số thuế đang khoá tay nếu có → tính **thực nhận** → ghi dòng lương → ghi lại bản sao các khoản danh mục |

**Khi chỉ sửa một ô rồi bấm “Lưu”:** hệ thống **bỏ qua các bước 4 → 11**. Nó dựng lại tổng thu trước phạt **từ các cột đã lưu sẵn trên dòng**, rồi chỉ chạy lại bước 12 → 14. Đây là gốc rễ của mọi lệch số ghi ở Phần 14.

---

# 2. CÔNG

## 2.1. Công chuẩn của tháng

**Tính thế nào**

> Công chuẩn = **số ngày làm việc thực của tháng theo lịch công ty**.
>
> Xét từng ngày trong tháng:
> - Ngày khai loại **“Làm bù”** → tính là ngày làm việc.
> - Ngày khai loại **“Nghỉ lễ”** hoặc **“Nghỉ — đi làm chỉ lương chính (1×)”** → **không** tính.
> - Các ngày còn lại → theo **Tuần làm việc chuẩn** (thứ nào bật, thứ nào tắt).
>
> Chưa cấu hình lịch ⇒ lấy công chuẩn dự phòng **26**. Nếu vẫn ra 0 ⇒ ép về **26,0**.

**Số lấy ở đâu**
Màn **Chấm công → tab “Lịch & Ngày lễ”**: khối “Tuần làm việc chuẩn” và khối “Ngày lễ & làm bù”.
Trên màn Lương, ô “Công chuẩn / tháng” hiện chữ **“Tự tính theo Lịch & Ngày lễ”** — **không gõ tay được nữa**, đừng đi tìm ô đó.

**Khi nào KHÔNG áp dụng**
Không có ngoại lệ. Công chuẩn tính **một lần cho cả kỳ**, dùng chung cho **mọi nhân viên** — không cá biệt hoá theo người, **không trừ theo ngày vào làm / nghỉ việc giữa tháng**. Nó được đóng băng vào kỳ lương và vào từng dòng lương.

**Dễ sai chỗ nào**

| # | Bẫy | Hậu quả |
|---|---|---|
| 1 | Công chuẩn **thay đổi theo từng tháng** | Cùng một người, cùng số giờ tăng ca, hai tháng ra hai số tiền khác nhau — **không phải lỗi** |
| 2 | Ngày “Nghỉ 1×” **không** được đếm vào công chuẩn | Mẫu số không tăng dù hôm đó có người đi làm |
| 3 | Công chuẩn lấy theo lịch chung, **không theo ca, không theo bộ phận** | Tổ chạy ca 3 vẫn dùng chung mẫu số với văn phòng |
| 4 | Nếu công chuẩn ra 0 thì hệ thống âm thầm coi là 1 | Cả tháng lương nổ theo đơn giá 1 công = cả tháng lương. Luôn nhìn dòng “NC chuẩn” trên phiếu lương |

---

## 2.2. Công thực đi làm — tử số của lương theo công

**Tính thế nào**

> Công thực = tổng công **ngày đi làm**
> \+ tổng công **ngày lễ hưởng lương**
> \+ tổng công **ngày nghỉ phép có lương**
> \+ công **được hoàn** do phiếu đi muộn / về sớm có **tích chọn trừ vào phép năm**
> **− tổng công của các ngày “Nghỉ 1×”**
>
> Công của một ngày đi làm = (số phút làm nằm trong khung ca) ÷ (số phút chuẩn của ca), làm tròn 2 chữ số, **tối đa 1,00**.
> - Vào trễ trong phạm vi **dung sai của ca** ⇒ coi như đúng giờ.
> - **Thiếu chấm RA của ca chính ⇒ 0 công** (ngày treo).
>
> Công ngày lễ = 1,0 (bằng 0 nếu có đơn nghỉ **không lương** phủ lên ngày lễ).
> Công ngày phép = 1,0 nếu đơn có lương, 0 nếu đơn không lương.

**Số lấy ở đâu**
Lượt bấm vào/ra ở màn **Chấm công**; danh mục ca ở **Chấm công → Khai ca → A · Ca làm việc** (giờ vào, giờ ra, dung sai, **ô tích “Ca qua đêm”**); đơn nghỉ ở màn **Nghỉ phép**; phiếu ở **Chấm công → Đi muộn / về sớm / nghỉ nửa buổi**; ngày đặc biệt ở **Lịch & Ngày lễ**.
**Kỳ công đã chốt ⇒ Lương đọc bản đã chốt. Chưa chốt ⇒ tính trực tiếp.**

**Khi nào KHÔNG có**
Nhân viên **không được phân ca nào** và cũng không có phép, không có lễ ⇒ màn Lương đọc thành **0,0 công**. Hệ thống **không tự quy đổi lượt bấm thành nguyên công**. Người đã nghỉ việc mà không còn công, không còn khoán, không còn dòng lương thì bị loại khỏi bảng lương.

**Dễ sai chỗ nào**

1. Công thực **ĐÃ GỒM** ngày lễ hưởng lương và ngày phép có lương — **đừng cộng thêm lần nữa**. Cũng vì vậy hai loại ngày này **không** bị đếm là nghỉ không lương khi xét luật miễn bảo hiểm 14 ngày.
2. Công thực **có thể lớn hơn công chuẩn** (đi làm Chủ nhật, ngày lễ). Phần dôi bị trần cắt ở bước tính tiền.
3. Công của ngày “Nghỉ 1×” **đã bị trừ ra** khỏi công thực, nên số công trên màn Lương **không** bằng tổng các ô ngày trên lưới Bảng công tháng.
4. Đã bấm **“Chốt công tháng”** rồi thì Lương đọc bản chốt — sửa chấm công sau đó **không đổi được số** cho tới khi bấm “Mở lại kỳ công”.

---

## 2.3. Ngày “Nghỉ 1×” — nghỉ, nhưng đi làm chỉ hưởng một lần lương

Đây là ngày khai ở **Lịch & Ngày lễ** với loại **“Nghỉ — đi làm chỉ lương chính (1×, không hệ số)”**. Trên chú giải màn Khai ca nó hiện là **“Nghỉ 1×”**.

**Tính thế nào**

> Với mỗi ngày “Nghỉ 1×” mà nhân viên **có chấm công**:
> - công của ngày đó được gom riêng vào **công “Nghỉ 1×”**;
> - đồng thời **bị trừ khỏi công thực** ngay từ bên Chấm công.
>
> Sang màn Lương, phần này **không đi qua lương theo công** mà trả riêng, **không bị trần**, và nằm trong cột “Tăng ca”:
>
> **Tiền ngày “Nghỉ 1×” = Đơn giá ngày × công “Nghỉ 1×” × 1,0** (đúng một lần lương, không có hệ số cộng thêm).
>
> Khi xét luật miễn bảo hiểm 14 ngày thì **cộng trả lại** phần công này:
> Ngày nghỉ không lương = Công chuẩn − Công thực − Công “Nghỉ 1×” (không âm).

**Số lấy ở đâu**
Ngày đặc biệt khai ở **Chấm công → Lịch & Ngày lễ**. Hệ số 1× là **cố định, không có ô khai**.

**Khi nào KHÔNG có**
Ngày này được xét **trước** ngày lễ và trước ngày nghỉ tuần, nên nó không bao giờ rơi vào nhóm lễ hay nghỉ tuần. Ngày “Nghỉ 1×” **không bị phạt đi trễ / về sớm tự động**.
**Tổ đang bật “Lương khoán / sản lượng”, hoặc tổ bị TẮT công tắc “Tăng ca” ⇒ tiền ngày “Nghỉ 1×” MẤT SẠCH.**

**Dễ sai chỗ nào**

1. Vì bị trừ khỏi công thực nên công “Nghỉ 1×” **không lấp trần** ⇒ người làm ngày đó được trả trọn một lần lương **kể cả khi đã đủ công chuẩn**. Đây là **chủ ý**.
2. Tiền này nằm **trong cột “Tăng ca”**, không có cột riêng. Nhìn cột Tăng ca thấy có tiền dù nhân viên không tăng ca giờ nào là **đúng**.

---

## 2.4. Công có đơn — công thiếu nhưng có đơn, chỉ nuôi chuyên cần

**Tính thế nào**

> Ngày có **phiếu đi muộn / về sớm đã duyệt** (có khai số phút xin) mà **không** tích chọn trừ vào phép năm:
> - Nếu số phút xin **đủ bù** phần thiếu thật ⇒ công có đơn = (1 − công thực của ngày đó).
> - Nếu số phút xin **ít hơn** phần thiếu thật ⇒ công có đơn = số phút xin ÷ số phút cửa sổ ca.
>
> **Công có đơn KHÔNG cộng vào công thực, KHÔNG ra tiền công.** Nó chỉ vào tử số khi tính tỷ lệ chuyên cần.

**Số lấy ở đâu**
Màn **Chấm công → Đi muộn / về sớm / nghỉ nửa buổi** (tab “Duyệt phiếu”), các phiếu ở trạng thái **Đã duyệt**.

**Khi nào KHÔNG có — ba điều kiện, thiếu một là bằng 0**

| # | Điều kiện |
|---|---|
| 1 | Ngày đó **phải có chấm công** và nhân viên **phải có ca** hôm đó |
| 2 | Ngày đó **không** phải ngày lễ, **không** phải ngày “Nghỉ 1×”, **không** có đơn phép nguyên ngày |
| 3 | Phiếu trùng ngày đã có đơn phép nguyên ngày thì bị loại ra từ trước |

**Dễ sai chỗ nào**

1. **Đây là chỗ công nhân cãi nhau nhiều nhất**: ngày **chỉ có phiếu đã duyệt mà không bấm vào/ra buổi nào** thì **không sinh công có đơn** — mất **cả tiền công lẫn chuyên cần**, dù đã xin phép đàng hoàng.
2. Có đơn thì **giữ được chuyên cần** nhưng **vẫn mất tiền công** phần vắng. Hai thứ tách nhau, giải thích cho thợ đúng như vậy.
3. Phiếu **có tích chọn trừ vào phép năm** đi nhánh khác: công được **hoàn** vào công thực và vào công phép có lương, **không** sinh công có đơn (để không bù hai lần).
4. Phần bù bị kẹp theo số công thiếu **thật**, nên khai khống số phút cũng **không** đúc ra công ảo.

---

## 2.5. Công ngày nghỉ phép có lương

**Tính thế nào**

> Bước 1 — Công phép = số công phép đầu vào, nhưng không vượt quá công thực.
> Bước 2 — Công đi làm = Công thực − Công phép.
> Bước 3 — **Công đi làm lấp trần TRƯỚC**: Công đi làm được trả = min(Công đi làm, Công chuẩn).
> Bước 4 — **Công phép lấy phần DƯ**: Công phép được trả = min(Công phép, Công chuẩn − Công đi làm được trả).
>
> **Lương ngày phép = (Mức nền = Lương cơ bản + Lương trách nhiệm, đã nhân hệ số thử việc ÷ Công chuẩn) × Công phép được trả**
>
> ✅ **Sửa 17/08/2026:** trước đó chỉ lấy lương cơ bản. Nay ngày phép **cùng đơn giá với ngày đi làm** — nghỉ phép năm là ngày nghỉ CÓ LƯƠNG (Điều 113 hưởng nguyên lương).

**Số lấy ở đâu**
Số ngày phép nguyên ngày: màn **Nghỉ phép** (đơn đã duyệt). Phần công hoàn lẻ (0,5 công…): phiếu đi muộn / về sớm có tích chọn trừ phép. Mức lương: **cả hai ô “Lương cơ bản” và “Lương trách nhiệm”** trong cửa sổ **Thiết lập lương**.

**Khi nào KHÔNG có**
Đơn nghỉ **không lương** ⇒ 0 công phép ⇒ 0 đồng. Hồ sơ **chưa tách lương**, chỉ có một cục lương gộp cũ ⇒ hệ thống coi cả cục là lương cơ bản, nếu không ngày phép sẽ ra 0 đồng.

**Dễ sai chỗ nào**

1. ✅ **Sửa 17/08/2026 — ngày nghỉ phép năm nay trả ĐỦ lương cơ bản + lương trách nhiệm.** Trước đó chỉ trả lương cơ bản, nên ai có lương trách nhiệm mà nghỉ phép thì tổng lương công **thấp hơn mức nền tháng**. Nay nghỉ phép **không còn bị hụt đồng nào** — cùng đơn giá với ngày đi làm.
2. Trên phiếu lương, dòng **“Trong đó: lương ngày phép”** là số **NẰM TRONG** dòng “Lương theo công”. **Tuyệt đối không cộng lại vào tổng thu.** Nay nó cùng đơn giá với ngày đi làm, giữ tách riêng chỉ để giải thích trong lương công có bao nhiêu là ngày phép.
3. Thứ tự lấp trần (công đi làm trước, công phép sau) là **cố ý**, để người đi làm dôi công không bị trừ hai lần.

---

# 3. MỨC NỀN THÁNG & HỆ SỐ THỬ VIỆC

## 3.1. Mức nền tháng

**Tính thế nào**

> **Mức nền tháng = ô “Lương cơ bản (đóng BH)” + ô “Lương trách nhiệm”.**
> Nếu cả hai ô đều bằng 0 mà hồ sơ cũ có một cục lương gộp ⇒ lấy cục lương gộp đó.
> Chưa khai gì ⇒ mức nền = 0.
>
> **Mức nền hiệu lực = Mức nền × hệ số thử việc.**
> **Lương cơ bản hiệu lực = Lương cơ bản (đóng BH) × hệ số thử việc.**

**Số lấy ở đâu**
**Lương → tab “Lương nhân viên” → nút “Thiết lập lương”**, bảng “Lương & phụ cấp cố định”.
Bản ghi lương được dùng là **bản có ngày hiệu lực lớn nhất mà vẫn ≤ NGÀY CUỐI THÁNG**; nếu hai bản cùng ngày thì bản mới hơn thắng. Xem lịch sử ở bảng “Lịch sử điều chỉnh” cuối cửa sổ đó.

**Khi nào KHÔNG có**
Không khai lương ⇒ mức nền 0 ⇒ lương công 0, **hệ thống không báo lỗi**, dòng lương vẫn được tạo ra bình thường.

**Dễ sai chỗ nào**

1. **Tra mức lương theo NGÀY CUỐI THÁNG, không phải ngày 01.** Đổi lương giữa tháng thì **cả tháng ăn mức MỚI**, không chia đôi theo ngày hiệu lực.
2. Mức đóng bảo hiểm **chỉ bám ô “Lương cơ bản (đóng BH)”**, không bám mức nền.

## 3.2. Hệ số thử việc

**Tính thế nào**

> Trạng thái tại kỳ là **thử việc** ⇒ nhân hệ số khai ở ô **“% lương thử việc”** (mặc định **80%**).
> Còn lại ⇒ nhân 1,0.

**Có HAI trạng thái cùng bị nhân hệ số này, đừng nhầm là một:**

| Trạng thái trên hồ sơ | Nghĩa là gì | Hệ số |
|---|---|---|
| **Thử việc** | Chưa tới ngày hết thử việc | 80% |
| **Hết thử việc · chờ xác nhận** | Đã qua ngày hết thử việc, **hệ thống tự đổi**, nhưng Hành chính nhân sự **chưa bấm** “Chuyển chính thức” | **vẫn 80%** |
| **Chính thức** | HCNS đã bấm xác nhận | 100% |

Nói cách khác: **máy chỉ đổi cái NHÃN, không đổi ĐỒNG NÀO.** Người ở trạng thái giữa vẫn nhận lương thử việc, vẫn không bị trừ bảo hiểm và đoàn phí — y hệt tháng trước đó. Tiền chỉ đổi ở kỳ lương **sau khi** HCNS bấm chuyển chính thức, và đổi từ **ngày hiệu lực** ghi trên nút bấm đó.

> ⚠️ **Chỗ này công ty đang làm khác luật, và là cố ý.** Bộ luật Lao động coi người làm tiếp sau khi hết thử việc là đã chính thức, tức đáng lẽ hưởng đủ 100% kể từ ngày hết hạn. Để càng lâu mới bấm thì phần trả thiếu càng dồn. Nếu thấy ô **“Chờ xác nhận”** trên màn Nhân sự có số, báo HCNS bấm sớm.

**Áp vào đúng 2 số gốc:** mức nền hiệu lực và lương cơ bản hiệu lực. Từ đó lan xuống: lương theo công, lương ngày phép, đơn giá ngày, đơn giá giờ, và vì thế lan tiếp sang tăng ca, phần cộng thêm lễ / nghỉ tuần, tiền ngày “Nghỉ 1×”, phụ cấp ca đêm.

**KHÔNG áp vào:** chuyên cần · phụ cấp khác · phụ cấp thâm niên · lương khoán · cơm ca · phụ cấp ca · mọi khoản thưởng · khoản danh mục.

**Ngoài ra, thử việc thì bảo hiểm = 0 và đoàn phí = 0.**

**Số lấy ở đâu**
Ô **“% lương thử việc”** ở **Lương → Cấu hình lương → Cơ chế lương theo bộ phận**, thẻ “Áp dụng toàn công ty”. Trạng thái thử việc lấy theo **lịch sử tại ngày cuối tháng**, không phải trạng thái hôm nay của hồ sơ ⇒ tính lại kỳ cũ vẫn ra đúng số cũ.

**Dễ sai chỗ nào**
Thử việc **vẫn hưởng đủ 100%** chuyên cần, phụ cấp, cơm ca, thưởng. **Chỉ** phần lương theo công và tăng ca bị nhân 80%. Không có khoản nào bị cấm hẳn với người thử việc.

---

# 4. LƯƠNG THEO CÔNG · CHUYÊN CẦN · PHỤ CẤP · THƯỞNG

## 4.1. Lương theo công — cột “Lương công”

**Tính thế nào**

> **Đơn giá ngày = Mức nền hiệu lực ÷ Công chuẩn**
>
> **Lương theo công = Đơn giá ngày × Công đi làm được trả + (Lương cơ bản hiệu lực ÷ Công chuẩn) × Công phép được trả**
>
> trong đó Công đi làm được trả = min(Công thực − Công phép, Công chuẩn).

Diễn giải cho đúng:

> Làm **đủ hoặc dôi** công ⇒ nhận **nguyên lương tháng**, **trừ phần ngày phép chỉ được tính theo lương cơ bản**.
> Làm **thiếu** công ⇒ chia theo tỷ lệ công thực trên công chuẩn.

**Số lấy ở đâu**
Công: **Chấm công → Bảng công tháng**. Mức lương: cửa sổ **Thiết lập lương**. Công chuẩn: **Lịch & Ngày lễ**.

**Khi nào KHÔNG có**
Không khai lương ⇒ 0 đồng, im lặng. Không có công ⇒ 0 đồng.

**Dễ sai chỗ nào**

1. **Dôi công không ra thêm tiền ở cột này.** Tiền làm ngày lễ / Chủ nhật đi qua **cột “Tăng ca”**. Nếu tổ bị **tắt công tắc “Tăng ca”** thì đi làm ngày lễ / Chủ nhật chỉ được một lần lương đã nằm sẵn trong lương công.
2. Mẫu số **luôn là công chuẩn**, không bao giờ chia cho công thực.
3. Trần công chuẩn áp cho **tổng** (công đi làm + công phép), không áp riêng từng loại.
4. Tổng các cột đã làm tròn **không nhất thiết bằng** tổng thu (tổng thu làm tròn một lần trên tổng). Lệch vài đồng là bình thường.

---

## 4.2. Chuyên cần — cột “Chuyên cần”

**Tính thế nào**

> Số ngày nghỉ = Công chuẩn − (Công thực + Công có đơn), không âm.
> Tỷ lệ hưởng = 1 − 0,5 × Số ngày nghỉ, không âm, tối đa 1,0.
> **Chuyên cần = Mức thưởng chuyên cần của nhân viên × Tỷ lệ hưởng.**

**Bảng nấc (ví dụ công chuẩn 26, mức khai 300.000 đ):**

| Công (thực + có đơn) | Số ngày nghỉ | Tỷ lệ | Số tiền |
|---|---|---|---|
| 26,0 trở lên | 0 | 100% | 300.000 |
| 25,5 | 0,5 | 75% | 225.000 |
| 25,0 | 1,0 | 50% | 150.000 |
| 24,5 | 1,5 | 25% | 75.000 |
| 24,0 trở xuống | 2,0 trở lên | 0% | 0 |

**Số lấy ở đâu**
Mức tiền khai ở ô **“Thưởng chuyên cần”** trong cửa sổ **Thiết lập lương** — **đây là nơi duy nhất khai tiền chuyên cần**.
Công tắc bật/tắt theo **tổ**: **Lương → Cấu hình lương → Cơ chế lương theo bộ phận**, công tắc **“Chuyên cần”**. Tổ chưa khai dòng nào ⇒ **mặc định BẬT**.

**Khi nào KHÔNG có**
Tổ tắt công tắc “Chuyên cần” ⇒ 0 đồng dù nhân viên có khai tiền. **Không có mức chuyên cần cấp tổ, cũng không có mức mặc định toàn công ty** — chưa khai ở hồ sơ nhân viên là 0 đồng.

**Dễ sai chỗ nào**

1. **Bậc nửa ngày mất 25%.** Nghỉ 2 ngày là **mất sạch**, không giảm tuyến tính.
2. Đi làm dôi công **không** được cộng thêm chuyên cần (tỷ lệ chặn ở 1,0).
3. Công có đơn được bù vào **tử số riêng cho chuyên cần** ⇒ có trường hợp chuyên cần đủ 100% mà tiền công vẫn thiếu. Không phải lỗi.
4. **Không** nhân hệ số thử việc.

---

## 4.3. Phụ cấp — cột “Phụ cấp”

**Tính thế nào**

> **Cột “Phụ cấp” = Phụ cấp khác (khai tay) + Phụ cấp thâm niên + Tổng các khoản danh mục loại “Thu” gán ở HỒ SƠ nhân viên.**
>
> Khoản danh mục **phát sinh riêng của kỳ** loại “Thu” ⇒ **cộng thẳng vào tổng thu, KHÔNG vào cột Phụ cấp**.
> Khoản danh mục loại **“Trừ”** (cả hai nguồn) ⇒ **trừ ở thực nhận, không vào tổng thu**.

Tất cả **cộng phẳng**: không chia theo công, không nhân hệ số thử việc, không vào gốc tính tăng ca.

**Số lấy ở đâu**
Ô **“Phụ cấp thâm niên”** và bảng **“Khoản thu nhập theo danh mục”** trong cửa sổ **Thiết lập lương**.
Khoản phát sinh riêng của kỳ: cửa sổ **“Sửa lương”**, khối **“Khoản phát sinh tháng này”**, nút **“+ Thêm khoản phát sinh”**.
Danh mục các khoản (tên, loại Thu/Trừ, chịu thuế hay miễn thuế): **Lương → Cấu hình lương → Danh mục khoản thu nhập**.

**Mức tiền của khoản danh mục chỉ có MỘT nơi khai: gán trực tiếp cho từng nhân viên.** Danh mục khoản chỉ giữ tên, loại và **ô tích chịu thuế** — **không có mức tiền mặc định theo nhóm**.

### ⚠️ Ô “Các khoản phụ cấp (số cũ, gộp một cục)” — cửa sổ Sửa lương

Ô này hiển thị **MỜ và không gõ được**, nhưng **ĐỪNG hiểu nhầm là đã ngưng trả**: số tiền trong ô **VẪN ĐƯỢC CỘNG ĐỦ** vào lương hằng tháng của nhân viên, y như trước. Ô chỉ hiện khi số cũ còn khác 0; nhân viên nào đã về 0 thì ô biến mất khỏi màn hình.

Đây là số phụ cấp kiểu cũ, gộp chung một cục (xăng xe, điện thoại, kiêm nhiệm…). Cách làm mới là tách ra từng khoản riêng ở bảng **“Khoản thu nhập”** phía trên.

**CẢNH BÁO CỘNG HAI LẦN:** hệ thống cộng **THÊM** các khoản mới tách **LÊN TRÊN** số cũ, chứ không tự thay thế. Nếu đã tách xong mà vẫn để nguyên số cũ trong ô này, nhân viên sẽ được trả **gấp đôi** phần phụ cấp đó, và sai **lặp lại MỖI THÁNG** cho tới khi phát hiện.

**Quy trình đúng, làm đủ 3 bước trong CÙNG một lần mở cửa sổ:**

1. Tách số cũ thành từng khoản riêng ở bảng “Khoản thu nhập” (bấm **“+ Thêm khoản thu nhập”**, nhập đúng tên và số tiền từng khoản). Cộng lại phải bằng đúng số cũ.
2. Bấm dòng chữ **“Đưa về 0 sau khi đã tách”** nằm ngay dưới ô (dòng chữ hướng dẫn màu xám) — ô sẽ về 0.
3. Bấm **“Lưu điều chỉnh”**. Bỏ qua bước 3 thì số 0 **KHÔNG** được ghi lại, và tháng sau vẫn trả hai lần.

**Kiểm lại sau khi lưu:** mở lại cửa sổ Sửa lương, ô “số cũ, gộp một cục” **phải biến mất hẳn**. Còn thấy ô đó là chưa xong.

**Yên tâm về lịch sử:** đưa về 0 chỉ áp dụng từ nay về sau; các mốc lương cũ trong **“Lịch sử điều chỉnh”** vẫn giữ nguyên số để tra cứu, không mất dữ liệu.

**Khi nào KHÔNG có**
Dòng khoản để trống hoặc bằng 0 ⇒ bỏ qua. Khoản danh mục **đã tắt (ngừng áp dụng)** mà nhân viên còn giữ ⇒ **vẫn trả**.

**Dễ sai chỗ nào**

1. Dòng **“Phụ cấp thâm niên”** trên phiếu lương là số **nằm trong** cột Phụ cấp — **đừng cộng lại**.
2. **Hai danh sách khoản danh mục phải để riêng**: khoản gán ở hồ sơ đã nằm trong cột Phụ cấp, khoản phát sinh của kỳ thì không. Nối hai danh sách lại là **cộng đôi tiền**.
3. Ô **“Phụ cấp ca (đã ngưng)”** trong cửa sổ Thiết lập lương chỉ để tra số cũ — **khai bao nhiêu cũng không ra tiền**.
4. **Phụ cấp trách nhiệm không nằm ở đây.** Nó là ô **“Lương trách nhiệm”**, nằm trong mức nền, nên **có** chia theo công.

---

## 4.4. Thưởng, lương ngày phép gõ tay, trả đồng phục

**Tính thế nào**

> Cộng thẳng vào tổng thu: Thưởng 5S + Thưởng doanh số + Thưởng thành tích + Phép năm + Trả đồng phục + Điều chỉnh lương.
> Riêng **Điều chỉnh lương cộng theo dấu**, nên **có thể âm** (chi tiết ở mục 4.5).

**Số lấy ở đâu — ĐỌC KỸ, đã đổi cách khai**

> **Sáu khoản thưởng cũ** (Phép năm · Thưởng 5S · Thưởng doanh số · Thưởng thành tích · Trả đồng phục · Thưởng khác) **đã bị GỠ khỏi cửa sổ Sửa lương** — **không khai mới được nữa**. Chúng chỉ còn hiện trong khối **“Khoản kỳ cũ”** có gắn nhãn **“chỉ đọc”**, và chỉ hiện khi kỳ cũ còn số.
>
> **Thưởng mới khai qua khối “Khoản phát sinh tháng này”** trong cửa sổ Sửa lương.

Bấm **“↻ Tính lại”** **giữ nguyên** các ô này của dòng đã có, không tính lại chúng.

**Khi nào KHÔNG có**
Kỳ đã chốt hoặc đã chi ⇒ toàn bộ khối “Khoản phát sinh tháng này” **chỉ để xem**, có dòng chữ “Kỳ lương đã chốt / đã chi — khối này chỉ để xem.”

**Dễ sai chỗ nào**

1. Ô **“Phép năm”** (kỳ cũ, gõ tay) **khác hẳn** dòng **“Lương ngày phép”** (tự tính, đã nằm trong lương theo công). Trùng tên trong đầu là **cộng đôi tiền phép**.
2. Toàn bộ nhóm này là **thu nhập chịu thuế**.

---

## 4.5. “Điều chỉnh lương” và “Giảm trừ khác” — HAI khoản khác nhau, KHÔNG phải một khoản hai mặt

Đây là **hai ô số riêng biệt**, nằm ở **hai bên đối lập** của phiếu lương. Đừng đối chiếu chéo hai khoản này với nhau.

**Bảng so sánh nhanh**

| | Điều chỉnh lương | Giảm trừ khác |
|---|---|---|
| Nằm ở bên nào của phiếu lương | Bên THU (khoản cộng) | Bên TRỪ (khoản trừ) |
| Vào tổng thu nhập? | CÓ — cộng thẳng vào Tổng thu | Không |
| Có chịu thuế TNCN không? | CÓ — nhập vào là TNCN tăng theo | Không làm giảm thu nhập chịu thuế |
| Có bị kẹp trần 30% (Điều 102) không? | KHÔNG | CÓ |
| Nhập ở đâu | Không có ô nhập trên màn hình (xem lưu ý dưới) | Cửa sổ “Sửa lương”, ô **“Giảm trừ khác (trừ)”** |
| Nhập số âm được không | Được (hệ thống không chặn) | Không — chỉ nhận số từ 0 trở lên |

**Rổ bị kẹp trần 30% gồm đúng 6 khoản, cộng lại rồi mới so với trần:**
Giảm trừ khác · Đi trễ / nghỉ không phép · Điện thoại vượt trội · Phạt biên bản · Đồng phục / phạt 5S · Trừ lỗi hàng khoán.
Trần = 30% của lương tháng sau khi đã trích BHXH và thuế TNCN. Phần vượt trần **bị bỏ luôn, KHÔNG dồn sang tháng sau**. **“Điều chỉnh lương” KHÔNG nằm trong rổ này.**

**Cùng một ô nhưng bốn tên gọi — đừng đếm thành bốn khoản:**

- Bảng lương tháng (cột thứ 11): **“Vi phạm”**
- Cửa sổ Sửa lương: **“Giảm trừ khác (trừ)”**
- Phiếu lương in ra: **“Giảm trừ khác”**
- File Excel bảng lương xuất ra: **“Vi phạm”**

Bốn tên trên là **CÙNG MỘT SỐ TIỀN**.

**Lưu ý về ô “Điều chỉnh lương” (bản hiện tại):**

- Không có ô nhập ở cửa sổ “Sửa lương”, không có cột trên bảng lương tháng, không có cột trong file Excel xuất ra. Nó chỉ hiện **một dòng trên phiếu lương in ra**, và chỉ khi số khác 0. Nghĩa là hiện kế toán **không có đường nào nhập tay khoản này từ màn hình** — chỉ còn số của kỳ cũ sót lại.
- Vì file Excel không có cột này, nếu dòng nào có số ở “Điều chỉnh lương” thì **cộng ngang các cột khoản trong Excel sẽ KHÔNG khớp cột “Tổng”**. Gặp lệch kiểu này thì mở phiếu lương của người đó ra xem có dòng “Điều chỉnh lương” không.
- **KHÔNG dùng “Điều chỉnh lương” với số âm để thay cho tiền phạt.** Làm vậy khoản phạt sẽ **lọt khỏi trần 30%** và còn **làm giảm thuế TNCN** — sai bản chất khấu trừ kỷ luật. Mọi khoản phạt phải đi vào ô **“Giảm trừ khác”** hoặc các ô phạt chuyên dụng.

(Đã kiểm lại: ô “Giảm trừ khác (trừ)” ở cửa sổ Sửa lương và cột “Vi phạm” trên bảng lương **đều đang bật**, không bị ẩn.)

---

## 4.6. Hoa hồng nhân viên kinh doanh — **HỆ THỐNG ĐÃ TỰ TÍNH** (từ 21/08/2026)

Trước 21/08/2026 mục này ghi "hệ thống chưa làm, phải tính tay". **Nay không phải tính tay nữa** — và **đừng nhập tay nữa**, nhập thêm là trả hai lần.

### Hệ thống tính thế nào

Mỗi tháng, với từng nhân viên kinh doanh, hệ thống cộng lại **các hoá đơn bán đã xuất trong tháng** của những đơn hàng do người đó đứng tên, rồi nhân với **% hoa hồng của từng đơn**:

> **Hoa hồng tháng = Σ (tiền hoá đơn **chưa gồm VAT**) × (% hoa hồng của đơn)**

Ba điều cần nhớ:

1. **Có hoá đơn là có hoa hồng — không chờ khách trả tiền.** Mốc là lúc *ra công nợ phải thu*, tức lúc xuất hoá đơn bán.
   ⚠️ Nghĩa là hoa hồng **trả trước khi tiền về**. Khách nợ xấu thì tiền đã chi rồi, muốn đòi lại phải trừ ở kỳ lương sau.
2. **Chỉ tính trên phần chưa có VAT.** Hoá đơn 108.000.000đ của đơn 100.000.000đ + VAT 8% ⇒ hoa hồng 5% tính trên **100 triệu**, ra 5.000.000đ (không phải 5.400.000đ). VAT là tiền thu hộ nhà nước.
3. **Một đơn xuất nhiều hoá đơn thì mở dần theo từng hoá đơn.** Xuất nửa đơn tháng này thì tháng này ăn nửa hoa hồng.

**Không tính:** hoá đơn đã **huỷ** · hoá đơn của **tháng khác** · đơn của **người khác** · đơn có **% hoa hồng = 0**.

### % hoa hồng lấy ở đâu

Ô **“% hoa hồng (NV kinh doanh)”** trong cửa sổ **Thiết lập lương** (và bước “Lương & BHXH” của cửa sổ Thêm nhân viên) **nay đã ra tiền thật**.

Số này được **chụp lại vào đơn hàng ngay lúc CHỐT đơn**. Nghĩa là:

- Sửa % cho một người **từ tháng sau** ⇒ **không** làm đổi hoa hồng của những đơn **đã chốt** trước đó. Tiền đã hứa thì không sửa ngược.
- % mới chỉ ăn vào **đơn chốt từ lúc sửa trở đi**.

### Nhìn thấy ở đâu trên bảng lương

Một dòng tên **“Hoa hồng kinh doanh”** trong khối **“Khoản thu nhập theo danh mục”** của cửa sổ **Sửa lương**, có nhãn **“Hệ tự tính”**, và cộng vào cột **“Thưởng”** trên bảng lương lẫn file Excel xuất ra.

**Dòng này KHÔNG sửa được, KHÔNG gỡ được** — cố tình như vậy:

- Sửa số ở đây thì lần bấm **“Tính lại”** kế tiếp sẽ ghi đè mất, mà không báo gì.
- Gỡ dòng đi cũng vô ích: tính lại là nó hiện lại.

**Sai số thì sửa ở đâu:**

- **Đơn đã chốt rồi thì % của nó KHÔNG sửa được nữa** — kể cả nhân sự, kể cả người bán. Cố ý như vậy: nếu sửa được thì người bán tự đặt được hoa hồng cho chính đơn mình bán. Sai thì bù bằng khoản **“Thu nhập khác (chịu thuế)”**.
- **Muốn đổi % cho các đơn SAU:** sửa ô *“% hoa hồng (NV kinh doanh)”* trong **Thiết lập lương**. Số mới chỉ ăn vào đơn chốt từ lúc đó trở đi.
- **Sai ở hoá đơn** (số tiền, ngày, xuất nhầm): sửa/huỷ hoá đơn rồi bấm **Tính lại** — hoa hồng chạy theo.

⚠️ **Thứ tự làm cho đúng:** khai % cho nhân viên **TRƯỚC**, rồi mới chốt đơn. Chốt đơn trước rồi mới khai % thì đơn đó vĩnh viễn không có hoa hồng.

**Thuế:** khoản này **chịu thuế TNCN** (khai ở danh mục khoản thu nhập, không đóng đinh trong máy).

**Không đóng BHXH trên khoản này.**

⚠️ **Đừng nhập tay hoa hồng vào “Khoản phát sinh tháng này” nữa.** Hệ thống đã tự tính rồi; nhập thêm một khoản “Hoa hồng” nữa là **trả hai lần**. Hệ thống có chặn khi bạn đặt tên khoản mới là “Hoa hồng”, nhưng đặt tên khác thì nó không đoán được.

---

# 5. TĂNG CA · CƠM CA · PHỤ CẤP CA ĐÊM

## 5.1. Đơn giá giờ — gốc nhân mọi hệ số

> **Đơn giá ngày = ô “Lương cơ bản (đóng BH)” × hệ số thử việc ÷ Công chuẩn**
> **Đơn giá giờ = Đơn giá ngày ÷ Giờ công chuẩn / ngày** (mặc định **8**)

Lưới an toàn: công chuẩn bằng 0 ⇒ ép thành 1,0. Giờ công chuẩn / ngày bằng 0 hoặc chưa khai ⇒ ép thành 8. Màn Cấu hình lương cũng chặn không cho khai giờ công chuẩn nhỏ hơn hoặc bằng 0.

**Dễ sai chỗ nào**

1. ⚠️ **ĐỔI TỪ 12/08/2026 — gốc tính tăng ca CHỈ là ô “Lương cơ bản (đóng BH)”.** Trước đó có cộng cả “Lương trách nhiệm”. **Ai có lương trách nhiệm thì tiền tăng ca GIẢM.** Ví dụ cơ bản 8tr + trách nhiệm 2tr, công chuẩn 26, 10 giờ tăng ca ngày thường: trước **721.155đ**, nay **576.930đ**.
   Giảm theo cả **phần cộng thêm ca đêm** và **phần cộng thêm làm ngày nghỉ / lễ** — ba khoản dùng chung một đơn giá.
   **Cột “Lương công” KHÔNG đổi** — nó vẫn tính trên mức nền đầy đủ. Ngày “Nghỉ 1×” cũng không đổi.
   Vẫn không gồm phụ cấp, chuyên cần, cơm ca.
2. Người thử việc bị nhân 80% vào **cả đơn giá tăng ca** — tăng ca của thử việc rẻ hơn 20%.
3. Công chuẩn thay đổi theo tháng ⇒ tháng ít ngày làm việc thì **đơn giá giờ cao hơn**. Cùng người, cùng số giờ tăng ca, hai tháng ra hai số — **không phải lỗi**.

---

## 5.2. BẢNG TRA HỆ SỐ TĂNG CA / LÀM NGÀY NGHỈ

| Tham số | Mặc định | Áp cho | Khai ở |
|---|---|---|---|
| **Tăng ca — ngày thường** | **1,5** | Giờ tăng ca ngày thường | Cấu hình lương → Cơ chế lương theo bộ phận |
| **Tăng ca — ngày nghỉ tuần** | **2,0** | Giờ tăng ca ngày nghỉ hàng tuần | như trên |
| **Tăng ca — ngày lễ** | **3,0** | Giờ tăng ca ngày lễ | như trên |
| **Làm nguyên công — ngày nghỉ tuần** | **2,0** | Cộng thêm **1 lần**; cộng với 1 lần đã có trong lương công ⇒ **tổng 2 lần** | như trên |
| **Làm nguyên công — ngày lễ** | **3,0** | Cộng thêm **trọn 3 lần**; cộng với 1 lần tiền ngày lễ ⇒ **tổng 4 lần** (sửa 17/08/2026) | như trên |
| Ngày **“Nghỉ 1×”** | **1,0** | Làm ngày “Nghỉ 1×” — trả **trọn 1 lần, không trần, không cộng thêm** | **Cố định, không có ô khai** |
| **Hệ số ca đêm của TỪNG CA** | **1,3** | Giờ đêm 22h–06h **trong ca**, chỉ ca qua đêm — **chỉ trả phần chênh 0,3 lần** | Chấm công → Khai ca → Ca làm việc |
| **Phụ cấp làm ban đêm** | **30%** | Phần đêm của **giờ tăng ca** ban đêm | Cấu hình lương |
| **Phụ cấp tăng ca đêm** | **20%** | Nhân với **hệ số LÀM NGUYÊN CÔNG của loại ngày** | Cấu hình lương |
| **Giờ công chuẩn / ngày** | **8** | Mẫu số ra đơn giá giờ | Cấu hình lương |

**Tổng hệ số cho 1 GIỜ TĂNG CA BAN ĐÊM (với cấu hình mặc định):**

| Loại ngày | Nằm ở cột “Tăng ca” | Nằm ở cột “Ca đêm” | **TỔNG** |
|---|---|---|---|
| Ngày thường | 1,5 | 0,3 + 0,2 × 1,0 = 0,5 | **2,0 → 200%** |
| Ngày nghỉ tuần | 2,0 | 0,3 + 0,2 × 2,0 = 0,7 | **2,7 → 270%** |
| Ngày lễ | 3,0 | 0,3 + 0,2 × 3,0 = 0,9 | **3,9 → 390%** |

---

## 5.3. Tiền tăng ca và phần cộng thêm ngày nghỉ / lễ — cột “Tăng ca”

**Tính thế nào**

> Giờ tăng ca ngày thường = (Tổng phút tăng ca **trừ** phút tăng ca ngày lễ **trừ** phút tăng ca ngày nghỉ tuần) ÷ 60
>
> **Tiền tăng ca =**
> Đơn giá giờ × [ Giờ tăng ca ngày thường × 1,5 + Giờ tăng ca ngày nghỉ tuần × 2,0 + Giờ tăng ca ngày lễ × 3,0 ]
> **+** Đơn giá ngày × [ Công ngày lễ × (3,0 − 1) + Công ngày nghỉ tuần × (2,0 − 1) + Công ngày “Nghỉ 1×” × 1,0 ]

**Hai điểm dễ tính sai ngay ở công thức:**

> (a) Số phút tăng ca trên bảng công là **TỔNG, đã gồm cả lễ, cả Chủ nhật, cả đêm** — phải **trừ ngược** ra mới có giờ tăng ca ngày thường. Ai tưởng nó là giờ ngày thường sẽ tính **dư tiền tăng ca lễ / Chủ nhật thêm một lần nữa**.
> (b) Phần cộng thêm bị **chặn sàn 0**. Nếu ai khai hệ số nhỏ hơn 1 ở Cấu hình lương thì phần cộng thêm ra 0, **không bao giờ ra số âm ăn bớt lương**.

**Số lấy ở đâu**
Phút tăng ca, phút tăng ca ngày lễ, phút tăng ca ngày nghỉ tuần, công ngày lễ, công ngày nghỉ tuần, công ngày “Nghỉ 1×”: lấy từ **Chấm công → Bảng công tháng** (bản đã chốt nếu kỳ công đã chốt). Hệ số: **Cấu hình lương → Cơ chế lương theo bộ phận**.

**Khi nào KHÔNG có — QUAN TRỌNG**

> **Toàn bộ khối trên bằng 0 — kể cả phần cộng thêm lễ / Chủ nhật và kể cả tiền ngày “Nghỉ 1×” — khi:**
> - tổ đang bật công tắc **“Lương khoán / sản lượng”**, **HOẶC**
> - tổ bị **TẮT công tắc “Tăng ca”** ở Cấu hình lương.

**Dễ sai chỗ nào**

1. ✅ **Đã sửa ngày 17/08/2026 — hai việc.**
   **(a)** Công ngày lễ / Chủ nhật **không còn bị trần công chuẩn cắt**. Trước đó người làm đủ công rồi còn đi làm thêm Chủ nhật chỉ nhận 1 lần; nay nhận đủ. Người **chưa** làm đủ công chuẩn thì số **không đổi**.
   **(b) Ngày lễ nay là 4 lần, không phải 3 lần.** Vì nghỉ lễ ở nhà thì vẫn có lương (1 lần); đi làm hôm đó được cộng thêm **trọn 300%** nữa. Ví dụ 1 công 200.000đ: tiền ngày lễ 200.000 + tiền làm thêm 600.000 = **800.000đ**.
   **Chủ nhật vẫn là 2 lần** — vì nghỉ Chủ nhật ở nhà **không** có lương, nên không có khoản nào để cộng thêm vào. Hai loại ngày khác nhau ở chỗ đó.
2. **Giờ tăng ca rơi vào ngày “Nghỉ 1×” tính hệ số NGÀY THƯỜNG 1,5**, không phải 2,0 hay 3,0.
3. Tăng ca bị tắt nhưng **phụ cấp ca đêm vẫn chạy** — bộ phận tắt tăng ca mà làm đêm vẫn có tiền đêm, ra con số lẻ 0,5 lần rất khó giải thích.

✅ **Sửa 17/08/2026 — tổ khoán VẪN CÓ tăng ca.** Trước đó bật “Lương khoán” cho một tổ là tổ đó **mất sạch** tiền tăng ca, tiền làm ngày lễ/Chủ nhật và tiền ngày “Nghỉ 1×”, trong khi cột Khoán vẫn bằng 0 vì nguồn sản lượng chưa nối. Nay hai công tắc **“Lương khoán”** và **“Tăng ca”** hoàn toàn độc lập, bật cả hai được.

---

## 5.4. Giờ tăng ca lấy từ chấm công — vai trò của phiếu tăng ca

**Tính thế nào**

> Trong một ngày công, các lượt bấm được ghép thành phiên:
> - **Phiên đầu tiên = CA CHÍNH** (giờ vào đầu tiên, giờ ra của ca chính) → dùng để tính **công**.
> - **Từ phiên thứ hai trở đi = TĂNG CA** → dùng để tính **giờ tăng ca**.
>
> Giờ bắt đầu tăng ca = giờ **VÀO** của phiên thứ hai.
> Giờ kết thúc tăng ca = giờ **RA của phiên CUỐI CÙNG** (không phải phiên thứ hai).
>
> Khoảng được tính tiền = phần **giao nhau** giữa khoảng bấm máy và khoảng ghi trên **phiếu tăng ca đã duyệt**.
>
> **Không có phiếu duyệt ⇒ 0 phút tăng ca. Thiếu cặp bấm của phiên tăng ca ⇒ 0 phút tăng ca.**

**Số lấy ở đâu**
Phiếu: màn **Tăng ca** (tab “Duyệt phiếu”, trạng thái Đã duyệt). Lượt bấm: **Chấm công → Bảng công tháng**, bấm vào ô ngày để mở chi tiết ngày.

**Khi nào KHÔNG có**
Không có phiếu đã duyệt phủ giờ đó ⇒ **0 đồng tăng ca**, dù bấm máy đầy đủ. Nhưng **vẫn đủ công ca chính** — chỉ mất tiền tăng ca.

**Ràng buộc phiếu:** tối đa **12 giờ một phiếu** (khai được từ 17/08/2026) · **tối đa 1 phiếu còn hiệu lực trong một ngày** · giờ kết thúc phủ được tới 48 giờ kể từ đầu ngày (để phủ ca đêm sang hôm sau).

✅ **TRẦN GIỜ LÀM THÊM THEO THÁNG (mới 17/08/2026).** Khai ở **Cấu hình lương → “Trần giờ tăng ca / tháng”**, đơn vị **giờ**. Luật cho tối đa **40 giờ/tháng**.
- **Chặn cứng:** hết trần thì **không tạo được phiếu nữa**, không có nút vượt, không xin ngoại lệ. Muốn cho làm thêm thì phải **nâng con số trong Cấu hình lương** — mà nó áp cho **cả công ty**, không riêng một người.
- **Phiếu đang chờ duyệt cũng chiếm chỗ.** Từ chối hoặc hủy phiếu là **trả chỗ lại ngay**.
- Con số đếm là **giờ đã đăng ký theo phiếu**, không phải giờ đã bấm máy — người về sớm hơn phiếu thì phần chênh vẫn giữ chỗ cho tới khi sửa hoặc hủy phiếu.
- **Mặc định là TẮT** (số 0). Bật bằng cách gõ 40 vào ô đó.
- **Không có trần theo NĂM.** Luật còn giới hạn 200 giờ/năm (một số ngành 300) nhưng hệ thống **không đếm** — chủ quyết bỏ. Ai cần theo dõi thì phải tự cộng ngoài.

**Dễ sai chỗ nào**

1. **Giao hai chiều**: về sớm hơn phiếu ⇒ trả theo **thực tế**; làm quá phiếu ⇒ **kẹp trần theo phiếu**. Giờ tăng ca nằm **ngoài** khung phiếu = **0 đồng** dù có bấm máy.
2. **Bắt buộc 2 cặp bấm**: phải chấm **RA ca chính** rồi **VÀO lại**. Ai ở lại làm tiếp mà không chấm ra ca chính thì phút tăng ca = 0 — **mất trắng tiền tăng ca**, bảng công chỉ hiện ngày treo.
3. Vì lấy **giờ ra của phiên cuối**, ai bấm ra–vào từ 3 lần trở lên trong buổi tăng ca thì **khe nghỉ giữa các phiên tăng ca vẫn được tính tiền**. Chỉ khe giữa “ra ca chính” và “vào tăng ca” là không tính.
4. Lúc bấm máy: sau khi ra ca chính, chấm vào lại **khi vẫn còn trong khung giờ ca** thì không cần phiếu. Chỉ khi **đã quá giờ tan ca** mới bắt buộc có phiếu. Nhưng đây chỉ là cửa gác lúc bấm máy — **tiền tăng ca thì luôn bị kẹp bởi phiếu**.

---

## 5.5. Ô “Phụ cấp ca (đã ngưng)” — luôn bằng 0

Ô này trong cửa sổ **Thiết lập lương** đang ở trạng thái **chỉ đọc, không sửa được**. Nó là đường cũ: một số phẳng gõ tay mỗi tháng. Đường đó **đã tắt**, thay bằng **cơm ca + phụ cấp ca theo ca thực làm** (mục 5.6).

Cột cũ vẫn giữ trên phiếu lương vì các kỳ lương cũ còn số trong đó, và số cũ đó **vẫn được miễn thuế**.

**ĐỪNG NHẦM hai cột:**

| Cột trên phiếu lương | Là gì | Trạng thái |
|---|---|---|
| **“Phụ cấp ca (khai tay — đã ngưng)”** | Số phẳng gõ tay mỗi tháng, đường cũ | **Luôn = 0 với kỳ mới** |
| **“Phụ cấp ca đêm (giờ × hệ số)”** | Tự tính theo giờ từ chấm công | **Đang dùng** |

**Bật lại đường khai tay mà không tắt khối cơm ca / phụ cấp ca theo ca = trả tiền hai lần.**

---

## 5.6. Cơm ca và phụ cấp ca theo ca thực làm

**Tính thế nào**

> Với mỗi ca mà nhân viên có đi làm:
> Số ngày hưởng = số ngày làm ca đó có **công của ngày ≥ ngưỡng** (ô “Công tối thiểu để hưởng cơm / phụ cấp ca”, mặc định **0,5**).
>
> **Tiền cơm ca = tổng của (Phụ cấp cơm của ca × Số ngày hưởng ca đó)** — mặc định 25.000 đ/ngày.
> **Tiền phụ cấp ca = tổng của (Phụ cấp ca của ca × Số ngày hưởng ca đó)** — mặc định 50.000 đ/ngày.
>
> **Hưởng trọn suất hoặc không hưởng** — cố ý không nhân theo tỷ lệ công.

**Số lấy ở đâu**
Mức tiền: **Chấm công → Khai ca → A · Ca làm việc**, ô **“Phụ cấp cơm (đ)”** và **“Phụ cấp ca (đ)”** của từng ca.
Ngưỡng: **Lương → Cấu hình lương → Cơ chế lương theo bộ phận**, ô **“Công tối thiểu để hưởng cơm / phụ cấp ca”**.
Số ngày từng ca: lấy từ Chấm công (đóng băng khi bấm “Chốt công tháng”).

**Khi nào KHÔNG có**
Chỉ đếm ngày **có đi làm**. **Nghỉ phép và nghỉ lễ không có suất.** Ca đã xoá khỏi danh mục thì bỏ qua, hệ thống không đoán mức.
**Không** bị tắt bởi công tắc lương khoán của tổ, **không** bị tắt bởi công tắc Tăng ca.

**Dễ sai chỗ nào**

1. **Trọn suất hoặc không**: đi muộn 15 phút (công 0,97) vẫn ăn **trọn 25.000 đ**, không ra 24.250 đ.
2. Tên là “phụ cấp ca” nhưng áp cho **mọi ca**, cả ca ngày lẫn ca đêm, không riêng ca đêm.
3. **Miễn thuế thu nhập cá nhân toàn bộ, không áp trần 730.000 đ/tháng** — xem Phần 13.
4. Khai ngưỡng bằng 0 thì **ngày treo (công 0) vẫn được suất**.
5. **Hai khoản này KHÔNG có cột riêng trên Bảng lương tháng** — chỉ thấy trên phiếu lương. Cộng ngang các cột của bảng lương sẽ không ra thực lĩnh.

---

## 5.7. Phụ cấp ca đêm theo giờ — cột “Ca đêm”

**Tính thế nào — hai phần cộng lại**

> **Phần A — giờ đêm nằm TRONG ca:**
> Ở màn Chấm công, mỗi ngày lấy số phút rơi vào khung **22:00–06:00 trong ca** rồi nhân với **(Hệ số ca đêm của ca − 1)**. Kết quả gọi là **phút đêm đã quy đổi**.
> **Phần A = Đơn giá giờ × phút đêm đã quy đổi ÷ 60.**
> **Chỉ cộng cho ca có tích chọn “Ca qua đêm”.** Ca ngày dù có giờ rơi vào 22h–06h thì phần A = 0.
>
> **Phần B — giờ TĂNG CA ban đêm (áp cho MỌI ca):**
> Đơn giá giờ × [ Giờ tăng ca đêm ngày thường × (30% + 20% × 1,0) + Giờ tăng ca đêm ngày nghỉ tuần × (30% + 20% × 2,0) + Giờ tăng ca đêm ngày lễ × (30% + 20% × 3,0) ]
>
> Số nhân với 20% là **hệ số LÀM NGUYÊN CÔNG** của loại ngày (2,0 / 3,0), **không phải** hệ số Tăng ca của loại ngày.

**Số lấy ở đâu**
Hệ số ca đêm: ô **“Hệ số ca đêm (vd 1.3 = +30%)”** của từng ca ở **Khai ca → Ca làm việc**.
Hai tỷ lệ 30% và 20%: ô **“Phụ cấp làm ban đêm”** và **“Phụ cấp tăng ca đêm”** ở **Cấu hình lương**.

**Khi nào KHÔNG có**
Phần A không có nếu ca **không** tích chọn “Ca qua đêm”. Cả hai phần **không** bị tắt bởi công tắc lương khoán của tổ, **không** bị tắt bởi công tắc Tăng ca.

**Dễ sai chỗ nào**

1. **“Phút đêm” đã nhân sẵn (hệ số − 1) ngay ở màn Chấm công rồi.** Màn Lương chỉ nhân đơn giá giờ. Ai tưởng đó là phút đêm thô rồi nhân hệ số lần nữa là **trả gấp đôi**.
   *Ví dụ:* 8 giờ đêm, ca hệ số 1,3 → 480 phút × 0,3 = **144 phút quy đổi** → đơn giá 125.000 đ/giờ × 144/60 = **300.000 đ**.
2. Ca đêm dùng **hệ số riêng của từng ca (1,3)**; tăng ca đêm dùng **tỷ lệ chung (30%)**. **Hai tham số khác nhau** — sửa một cái không đổi cái kia.
3. Phần B dùng **hệ số Làm nguyên công**, không dùng hệ số Tăng ca. Mặc định trùng số 2 và 3 nên không lộ; chỉnh lệch nhau là ra số khác ngay.
4. **Tiền một giờ tăng ca đêm nằm ở HAI DÒNG khác nhau trên phiếu lương.** Kế toán chỉ nhìn riêng cột “Tăng ca” sẽ thấy thiếu 25% và tưởng máy tính sai.

---

## 5.8. Ca qua nửa đêm — ngày công tính về ngày nào

**Tính thế nào**

> Với ca có tích chọn **“Ca qua đêm”**, mốc kết thúc ca được cộng thêm 24 giờ. Cửa sổ ca = mốc kết thúc − giờ vào ca.
>
> **Ngày công của một lượt bấm:** nếu là ca đêm và giờ bấm còn nằm trước hoặc bằng giờ kết thúc ca ⇒ tính về **ngày hôm trước**. Ngược lại tính về ngày lịch.
>
> Công = số phút làm ÷ cửa sổ ca, làm tròn 2 chữ số, tối đa 1,00.

**Dễ sai chỗ nào**

1. **Ngày công của ca đêm là NGÀY VÀO CA.** Toàn bộ phân loại lễ / nghỉ tuần / “Nghỉ 1×” bám ngày này. Ca đêm vào 30/04 kéo sang 01/05 vẫn tính hệ số theo **30/04**. Tăng ca của ca đêm thứ Bảy kéo sang rạng sáng Chủ nhật vẫn tính hệ số **ngày thường**.
2. Giờ đêm **trong ca** bị kẹp trần ở mốc kết thúc ca để loại phần tăng ca ra — nếu không thì giờ tăng ca đêm bị tính hai lần.
3. Cửa sổ ca bằng 0 hoặc âm ⇒ công = 0 và ngày bị đánh dấu lỗi. Kiểm lại giờ vào / giờ ra của ca đó.

---

# 6. LƯƠNG KHOÁN

## 6.1. Trạng thái thật — nói thẳng

> **Cột “Khoán” trên Bảng lương tháng hiện LUÔN BẰNG 0 cho mọi nhân viên.**
>
> Lý do: **phần khai sản lượng chưa dùng được** — không còn màn nhập sản lượng, không còn số liệu để cộng. Hệ thống **không báo lỗi, không cảnh báo** khi không có số nào để cộng.
>
> Nhân sự cũng **không gõ tay được** tiền khoán trong cửa sổ Sửa lương.
>
> **Hệ thống chưa làm phần này. Muốn trả khoán tháng này thì tính tay ngoài hệ thống rồi nhập vào “Khoản phát sinh tháng này”** (nhớ: khoản đó **chịu thuế**, đúng như khoán).

Cái đang chờ Lệnh sản xuất là **phần khác**: tiền khoán **dự kiến** ở bước lệnh sản xuất đã chạy và ra số thật, nhưng đó là **số kế hoạch, không chảy sang bảng lương**.

## 6.2. Đơn giá khoán — khai ở đâu và hệ thống chọn đầu việc thế nào

**Số lấy ở đâu**
**Lương → tab “Lương khoán”**, nút **“+ Thêm đơn giá”**: các ô **“Tổ”**, **“Công việc”**, **“Đơn vị”**, **“Đơn giá”**.

**Hệ thống chọn đầu việc thế nào khi lập lệnh sản xuất**

> Bước 1 — lọc theo **TỔ**: chỉ những đầu việc đang hiệu lực và **đúng tổ đó**.
> Bước 2 — lọc theo **CÔNG ĐOẠN**: giao với danh sách định mức đã khai cho công đoạn đó.
> Tự điền: có đúng một dòng định mức đánh dấu mặc định ⇒ lấy dòng đó; nếu không, chỉ có một đầu việc khớp tổ ⇒ lấy nó; còn lại để trống, bắt người lập chọn tay.

**Dễ sai chỗ nào**

1. **Công đoạn chưa khai dòng định mức nào ⇒ danh sách rỗng ⇒ bước đó không chọn được đầu việc nào**, dù tổ đã khai đầy bảng giá. Không có cách ghi đè.
2. Đơn giá khoán **chưa gắn tổ** thì **không bao giờ khớp** bước nào.
3. Ô “Đơn vị” lưu đúng chữ hiển thị. Gõ đơn vị ngoài danh sách gợi ý vẫn lưu ⇒ hai dòng cùng nghĩa mà chữ khác nhau sẽ không gộp được.

## 6.3. Tiền khoán theo người — cách tính khi phần khai sản lượng dùng được trở lại

> Tiền một phiếu = làm tròn của (Sản lượng × Đơn giá − Trừ lỗi), **chặn sàn 0 từng phiếu**.
> Khoán của nhân viên = tổng tiền các phiếu của người đó trong kỳ.
> Chỉ cộng phiếu có đánh dấu tính khoán và **có gán nhân viên**.

**Dễ sai chỗ nào** — Sàn 0 áp **từng phiếu**, không phải cả kỳ: phiếu lỗ nặng bị kẹp về 0 nhưng phiếu khác vẫn cộng đủ ⇒ tổng kỳ **khác** với công thức “tổng doanh thu khoán trừ tổng trừ lỗi”.

## 6.4. Khoán vào bảng lương — CỘNG THÊM

Cộng **phẳng và vô điều kiện**: không nhân hệ số thử việc, không chia theo công, không bị chặn trần công. Công tắc “Lương khoán / sản lượng” của tổ **không điều khiển việc cộng tiền khoán**.

**Dễ sai chỗ nào**

1. Khoán **CHỊU thuế thu nhập cá nhân** — khác hẳn tăng ca, ca đêm, cơm ca.
2. Khoán **không** vào mức đóng bảo hiểm và **không** vào đơn giá giờ tăng ca.

## 6.5. Loại trừ KHOÁN ⟷ TĂNG CA — **cảnh báo nặng nhất hiện nay**

> Nếu tổ bật **“Lương khoán / sản lượng”** **HOẶC** tắt công tắc **“Tăng ca”**:
> **Tiền tăng ca = 0** — nuốt cả phần cộng thêm ngày lễ / Chủ nhật và cả tiền ngày “Nghỉ 1×”.
>
> Quyết định theo **TỔ** (phòng ban tại thời điểm trả lương), **không** theo từng người và **không** phụ thuộc việc người đó có thực sự có tiền khoán hay không.

> ⚠️ **Tiền tăng ca bị ép về 0 dựa trên công tắc của TỔ, trong khi cột Khoán LUÔN bằng 0 vì phần khai sản lượng chưa dùng được.**
> ⇒ **Nhân viên tổ đang bật công tắc khoán MẤT tiền tăng ca mà KHÔNG được bù đồng khoán nào.**
> **Bật công tắc “Lương khoán / sản lượng” cho một tổ ngay lúc này = CẮT TĂNG CA của cả tổ.**
> **Cách xử lý: TẮT công tắc đó cho tới khi phần khai sản lượng dùng được trở lại.**

Bẫy phụ:

- Phụ cấp ca đêm **vẫn được trả** ⇒ giờ tăng ca đêm của tổ khoán chỉ được 0,5 lần thay vì 2,0 lần.
- **Hở một chiều**: sửa ô tích làm khoán ở màn **Phòng ban** **không** ghi gì vào bảng khoản lương; chỉ chiều từ **Cấu hình lương** mới ghi ngược lại. Hai nơi có thể lệch nhau — phải **kiểm lại cả hai màn**.
- Tổ chưa khai dòng nào: công tắc **“Tăng ca” mặc định BẬT**; công tắc “Lương khoán / sản lượng” lấy theo ô tích làm khoán của phòng ban.
- Nút gạt “Lương khoán / sản lượng” làm đúng hai việc rất lệch nhau: (a) hiện thẻ “Đơn giá khoán” của tổ, (b) qua ô tích của phòng ban mà **tắt tăng ca cả tổ**.

## 6.6. Thưởng / phạt tổ trưởng theo tỷ lệ hàng lỗi — **hệ thống chưa nối, khai không ra tiền**

Thẻ **“Thưởng / phạt tổ trưởng theo chất lượng”** ở Cấu hình lương cho khai bậc: nếu sản lượng dưới ngưỡng tối thiểu thì 0; ngược lại tiền = tổng khoán của tổ × tỷ lệ của bậc; tỷ lệ dương là thưởng, âm là phạt.

**Khai bậc trên màn hình KHÔNG ra đồng nào trên bảng lương.** Màn khai có băng cảnh báo nói đúng điều này — **đừng gỡ băng cảnh báo đó**.

## 6.7. Tiền khoán dự kiến ở Lệnh sản xuất — không chảy vào lương

Ở bước lệnh sản xuất, hệ thống quy đổi số lượng vào của bước sang đơn vị của đơn giá rồi nhân đơn giá đã ghim, cộng lại thành tổng lệnh.
*Ví dụ thật:* 241 tờ × 86 cm × 65 cm = 134,72 m² × 150 đ/m² = **20.208 đ**.

**Dễ sai chỗ nào** — Nhìn thấy “Công thợ dự kiến” có số mà bảng lương ra 0 là **đúng thiết kế hiện tại**, không phải lỗi. Bản ghim đầu việc là cố ý: xưởng lên giá khoán sau **không được xê dịch lệnh đã phát**. Ghi đè bản ghim mà chỉ điền lại mã, tên, đơn vị, đơn giá là **xoá mất định mức** ⇒ vỡ năng suất và thời lượng của bước.

---

# 7. TỔNG THU — LIỆT KÊ ĐẦY ĐỦ

> **TỔNG THU (trước phạt) =**
> Lương theo công *(đã gồm lương ngày phép)*
> \+ Chuyên cần
> \+ Phụ cấp *(phụ cấp khác + thâm niên + khoản danh mục gán ở hồ sơ, loại Thu)*
> \+ Các khoản phụ cấp số cũ gộp một cục *(nếu ô đó còn khác 0 — xem mục 4.3)*
> \+ Khoán
> \+ Tăng ca *(giờ tăng ca + phần cộng thêm lễ / nghỉ tuần + tiền ngày “Nghỉ 1×”)*
> \+ Phụ cấp ca khai tay *(luôn = 0 với kỳ mới)*
> \+ Phụ cấp ca đêm
> \+ Cơm ca + Phụ cấp ca theo ca
> \+ Thưởng khác / hoa hồng nhập tay *(đã chặn khai mới — hoa hồng nay hệ tự tính, xem §4.6)*
> \+ Thưởng chi tiết + Phép năm gõ tay + Trả đồng phục + Điều chỉnh lương *(cộng theo dấu)*
> \+ Khoản danh mục **phát sinh của kỳ**, loại Thu
>
> **TỔNG THU SAU PHẠT = TỔNG THU (đã làm tròn) − Phạt hiệu lực**, chặn sàn 0.

**KHÔNG có trong tổng thu:**

| Khoản | Lý do |
|---|---|
| Lương ngày phép | Đã nằm trong Lương theo công |
| Phụ cấp thâm niên | Đã nằm trong cột Phụ cấp |
| Giảm trừ khác (Vi phạm) | Là khoản **phạt**, trừ ở bước phạt và bị kẹp trần 30% |
| Khoản danh mục loại **Trừ** | Trừ ở thực nhận, cố ý không gộp vào trần 30% |
| Tạm ứng, lương đợt 1 | Trừ ở thực nhận |
| Bảo hiểm, đoàn phí, thuế | Trừ ở thực nhận |

**Dễ sai chỗ nào**

1. Tổng thu được làm tròn **một lần trên tổng** rồi mới trừ phạt ⇒ **tổng các cột đã làm tròn riêng có thể lệch vài đồng**. Bình thường.
2. ⚠️ **Khi sửa một ô rồi lưu, hệ thống dựng lại tổng thu từ các cột đã lưu.** Nếu một khoản thu nào đó bị sót ở đường này thì thao tác “sửa một ô” **ăn mất tiền người lao động trong im lặng**, bảng lương vẫn trông bình thường. Bệnh này **đã tái phát 3 lần**. Vì thế: **sửa xong luôn bấm “↻ Tính lại”.**

---

# 8. BHXH · BHYT · BHTN · ĐOÀN PHÍ CÔNG ĐOÀN

## 8.1. BẢNG TRA TỶ LỆ BẢO HIỂM

| Khoản | **Người lao động bị trừ** | Công ty đóng *(tham chiếu — không trừ nhân viên)* | Trần đóng |
|---|---|---|---|
| BHXH | **8%** | 17,5% | **50.600.000 đ** |
| BHYT | **1,5%** | 3% | 50.600.000 đ |
| BHTN | **1%** | 1% | **106.200.000 đ** |
| Tai nạn lao động – bệnh nghề nghiệp | — | 0,5% | — |
| **Cộng phía người lao động** | **10,5%** | 21,5% + 0,5% | |

> ⚠️ **Bốn ô tỷ lệ phía công ty** (cột “NSDLĐ (%)” của BHXH, BHYT, BHTN và ô “TNLĐ-BNN (công ty đóng)”) ở tab **Bảo hiểm & Thuế** trông y hệt các ô khác nhưng **sửa chúng không đổi một đồng nào** trên bảng lương. Chỗ duy nhất dùng đến là dòng hiển thị chi phí tai nạn lao động cho nhóm “Bảo hiểm đóng ở nơi khác”, và dòng đó **chỉ hiện trên màn Sửa lương, không ghi vào bảng lương**.
>
> ⇒ **Hệ thống chưa làm phần báo cáo tổng chi phí bảo hiểm phía công ty. Muốn có con số đó phải tính tay ngoài hệ thống.**

## 8.2. Mức đóng bảo hiểm

**Tính thế nào**

> **Mức đóng bảo hiểm = ô “Lương cơ bản (đóng BH)” + ô “Lương trách nhiệm”** (chính là **mức nền tháng**).
>
> **Không** nhân hệ số thử việc · **không** chia theo công · **không** cộng phụ cấp nào.

⚠️ **ĐỔI TỪ 12/08/2026.** Trước đó chỉ tính trên lương cơ bản. **Ai có lương trách nhiệm thì bị trừ bảo hiểm nhiều hơn trước** — trách nhiệm 2 triệu thì mất thêm khoảng **210.000đ/tháng**, và công ty cũng đóng thêm phần của mình. Nói trước với nhân viên, đừng để họ tự phát hiện trên phiếu lương.

**Số lấy ở đâu**
Cửa sổ **Thiết lập lương**, ô **“Lương cơ bản (đóng BH)”**.

**Dễ sai chỗ nào**

1. **Không chia theo công**: người đi làm 3 công trên 26 vẫn đóng bảo hiểm trên **toàn bộ** lương cơ bản (trừ khi rơi vào luật nghỉ không lương từ 14 ngày ở mục 8.4).
2. Mức đóng bảo hiểm nay **bằng đúng mức nền tính lương**. (Trước 12/08/2026 nó thấp hơn — nếu đối chiếu bảng cũ thấy lệch thì là do đổi luật này, không phải sai sót.)
3. Hồ sơ **cũ** chỉ khai một cục lương gộp ⇒ ô Lương cơ bản bằng 0 ⇒ **bảo hiểm = 0 VÀ đoàn phí = 0** mà bảng lương vẫn ra tiền bình thường, **không có cảnh báo nào**. Đây là lỗi hay gặp nhất với người mới nhập hồ sơ.
4. Ô “mức đóng bảo hiểm khai riêng” trên hồ sơ vẫn hiện nhưng **không còn được đọc** — gõ vào không đổi được gì.
5. Ô tích **“khoản này cộng vào gốc đóng BH”** ở Danh mục khoản thu nhập **không có tác dụng** — bật lên không thay đổi gì.
6. **Mức đóng bảo hiểm và tiền bảo hiểm bị đóng băng lúc bấm “↻ Tính lại”.** Sửa một ô rồi lưu **không** tính lại hai số này. **Sửa ô “Lương cơ bản (đóng BH)” ở hồ sơ mà không bấm “↻ Tính lại” thì bảng lương vẫn dùng số cũ.**

## 8.3. Tiền bảo hiểm trừ vào lương — cột “BHXH”

**Tính thế nào**

> Gốc BHXH + BHYT = min(Mức đóng bảo hiểm, **50.600.000**)
> Gốc BHTN = min(Mức đóng bảo hiểm, **106.200.000**)
>
> **Cột “BHXH” trên bảng lương = Gốc BHXH+BHYT × (8% + 1,5%) + Gốc BHTN × 1%**

**Hai trần áp riêng, không dùng chung.** Gõ **0** vào ô trần **không phải “miễn đóng”** mà là **“bỏ trần, đóng trên toàn bộ lương”**.

*Ví dụ lương cơ bản 60 triệu:* 50.600.000 × 9,5% + 60.000.000 × 1% = 4.807.000 + 600.000 = **5.407.000 đ**.

**Số lấy ở đâu**
Tỷ lệ và trần: **Lương → Cấu hình lương → Bảo hiểm & Thuế**, các ô “Trần đóng BHXH + BHYT”, “Trần đóng BHTN”, cột “NLĐ (%)”.

**Dễ sai chỗ nào**

1. **TÊN CỘT ĐÁNH LỪA**: cột “BHXH” trên Bảng lương tháng là **TỔNG CẢ BA** (8% + 1,5% + 1% = 10,5%), không phải riêng BHXH 8%.
2. **Phiếu lương tách 3 dòng theo cách khác:** dòng BHXH và dòng BHYT tính bằng phép nhân (8% và 1,5% trên gốc đã kẹp trần), còn **dòng BHTN là phần còn lại**: lấy cột tổng trừ đi hai dòng trên. Hai hệ quả: (a) ba dòng **luôn cộng đúng bằng** cột tổng — cố ý; (b) **nếu sau khi kỳ đã chốt mà ai đó sửa tỷ lệ hay trần bảo hiểm ở Cấu hình lương thì phiếu lương của kỳ CŨ đổi số ở hai dòng đầu và toàn bộ sai lệch dồn hết vào dòng BHTN — có thể ra số vô lý, kể cả số ÂM**, trong khi tổng trừ và thực nhận không đổi. **Kỳ đã chốt thì đừng động vào tab Bảo hiểm & Thuế.**
3. Cửa sổ Sửa lương hiện 3 dòng làm tròn riêng nên tổng hiển thị có thể lệch tối đa 2 đồng so với số thật.
4. Tiền bảo hiểm được trừ khi tính thu nhập **tính** thuế, và nằm trong mẫu số của trần phạt 30% ⇒ **sai mức đóng bảo hiểm là sai lây cả thuế lẫn trần phạt**.

## 8.4. BỐN NHÁNH BẢO HIỂM — theo đúng thứ tự ưu tiên

| # | Nhánh | Điều kiện | Mức đóng | Tiền bảo hiểm bị trừ | Đoàn phí |
|---|---|---|---|---|---|
| 1 | **THỬ VIỆC** | Trạng thái tại kỳ là thử việc | **0** | **0** | **0** |
| 2 | **Bảo hiểm đóng ở nơi khác** | Hồ sơ có tích chọn “Bảo hiểm đóng ở nơi khác” | = Lương cơ bản | **0** | **VẪN TRỪ** |
| 3 | **Nghỉ không lương từ N ngày** | Ngưỡng > 0 **VÀ** số ngày nghỉ không lương ≥ ngưỡng (mặc định **14**) | = Lương cơ bản | **0** | **VẪN TRỪ** |
| 4 | Nhánh thường | Còn lại | = Lương cơ bản | Theo mục 8.3 | Theo mục 8.5 |

> Số ngày nghỉ không lương = Công chuẩn − Công thực − Công ngày “Nghỉ 1×”, không âm.
> So sánh dùng dấu **≥** (đúng bằng ngưỡng là đã miễn). **Không làm tròn** trước khi so — nghỉ 13,5 ngày thì **chưa** miễn với ngưỡng 14.

**Số lấy ở đâu**
Ô tích **“Bảo hiểm đóng ở nơi khác — công ty chỉ đóng TNLĐ-BNN”** trong cửa sổ Thiết lập lương.
Ô **“Không đóng BHXH nếu nghỉ không lương từ”** ở tab Bảo hiểm & Thuế.

**Dễ sai chỗ nào**

1. Nhánh 1 là **nhánh duy nhất** đặt mức đóng bằng 0. Đọc phiếu thấy “Mức đóng BH 20 triệu, tiền bảo hiểm 0 đồng” thì đó là nhánh 2 hoặc nhánh 3 — **không phải lỗi**.
2. ⚠️ Khai ngưỡng bằng **0 nghĩa là TẮT LUẬT**, **không** phải “miễn cho mọi người”.
3. Nhánh 3 phủ luôn người **vào làm hoặc nghỉ việc giữa tháng** (ít công) — vào làm ngày 20 là **tự động không đóng bảo hiểm tháng đó**.
4. Phải **cộng trả lại công ngày “Nghỉ 1×”**; nếu quên, người đi làm ngày “Nghỉ 1×” bị đếm nhầm là nghỉ không lương và **mất bảo hiểm oan**.

## 8.5. Đoàn phí công đoàn

**Tính thế nào**

> Thử việc **hoặc** không phải đoàn viên ⇒ **0 đồng**.
> Còn lại: **Đoàn phí = Mức đóng bảo hiểm × Tỷ lệ đoàn phí**, làm tròn.

**Số lấy ở đâu**
Ô tích **“Đoàn viên công đoàn — có trừ đoàn phí công đoàn”** trong cửa sổ Thiết lập lương — **mặc định TẮT, phải bật cho từng người**.
Ô **“Đoàn phí công đoàn (NV đóng)”** ở tab Bảo hiểm & Thuế — **mặc định 0**, phải tự khai (mẫu 0,5%).

**Khi nào KHÔNG có**
Thử việc, hoặc chưa tích chọn đoàn viên, hoặc tỷ lệ chưa khai.

**Dễ sai chỗ nào**

1. Đoàn phí tính trên mức đóng bảo hiểm **GỐC, không kẹp trần**: lương cơ bản 60 triệu thì đoàn phí tính trên 60 triệu trong khi bảo hiểm chỉ tính trên 50,6 triệu.
2. **Vẫn trừ đoàn phí ở cả hai nhánh miễn bảo hiểm** — tháng không đóng bảo hiểm vẫn mất đoàn phí.
3. ⚠️ **ĐỔI TỪ 12/08/2026: đoàn phí CÓ giảm thu nhập tính thuế**, đi y hệt bảo hiểm — vừa là vế trừ khi tính thuế, vừa là tiền thật trừ vào thực nhận. **Không phải trừ hai lần**: một lần làm giảm số dùng để tra thuế, một lần là tiền thật ra khỏi lương.
4. ⚠️ Có lệch hai đường tính — xem Phần 14, lỗi số 3.

---

# 9. THUẾ THU NHẬP CÁ NHÂN

## 9.1. Thu nhập CHỊU thuế

**Tính thế nào**

> **Thu nhập chịu thuế = TỔNG THU (trước phạt) − 5 khoản miễn**, chặn sàn 0.
> **Thu nhập miễn thuế = tổng 5 khoản miễn.**

**NĂM KHOẢN MIỄN — đầy đủ:**

| # | Khoản | Ghi chú |
|---|---|---|
| 1 | **Tiền tăng ca** | Miễn **toàn bộ**, không có trần |
| 2 | Phụ cấp ca khai tay (đã ngưng) | Luôn 0 với kỳ mới; kỳ cũ vẫn được miễn |
| 3 | **Phụ cấp ca đêm** | Miễn cả phần trong ca lẫn phần cộng dồn của tăng ca đêm |
| 4 | **Khoản danh mục có tích chọn “Miễn thuế”** | Bốn khoản mẫu: trang phục, trợ cấp nhà ở, hỗ trợ đi lại, tiền cơm. Khoản khác (điện thoại, xăng xe…) **CHỊU** thuế |
| 5 | **Cơm ca + Phụ cấp ca theo ca** | Miễn toàn bộ, **không áp trần 730.000 đ/tháng** |

**KHÔNG miễn:** mọi khoản thưởng (5S, doanh số, thành tích, phép năm gõ tay, trả đồng phục, điều chỉnh lương, thưởng khác) và **KHOÁN**.

Cách tính này **áp cho cả ba chế độ thuế**, tính trước khi rẽ nhánh.

**Số lấy ở đâu**
Ô tích chịu thuế / miễn thuế của từng khoản: **Lương → Cấu hình lương → Danh mục khoản thu nhập**, cột **“Chịu thuế”**.

### ⚠️ Phiếu lương — 2 ô thuế đang bị ẩn (từ bản cập nhật giao diện ngày 03/08/2026)

Trên phiếu lương (**cả bản in do nhân sự xuất lẫn màn “Phiếu lương của tôi”** nhân viên tự xem — hai nơi dùng chung một mẫu), dải thuế nằm giữa bảng “Các khoản TRỪ” và dòng **THỰC NHẬN** hiện **không còn hiển thị**. Hai ô bị ẩn là:

- **Thu nhập tính thuế TNCN**
- **Thu nhập miễn thuế**

(cùng câu giải thích đi kèm hai ô này).

**Đây chỉ là ẩn khỏi mắt, KHÔNG phải ngừng tính và KHÔNG mất tiền:**

- Hệ thống vẫn tính và lưu đủ hai số này cho từng người, từng kỳ.
- Dòng **“Thuế TNCN”** ở cột Các khoản TRỪ **vẫn hiện** và vẫn bấm đúng trên số thu nhập tính thuế đó.
- **TỔNG THU, TỔNG TRỪ và THỰC NHẬN không thay đổi một đồng nào** (hai ô này chỉ là số thuyết minh, không cộng vào tổng) — **không cần đối chiếu lại phiếu đã in trước đó**.

**Khi cần tra số:** mở màn **Sửa lương** của người đó, dòng tóm tắt đầu màn vẫn ghi “… thu nhập tính thuế X → Thuế TNCN Y”. Riêng **“Thu nhập miễn thuế”** hiện **không còn chỗ nào tra trên màn hình** — cần thì đề nghị bộ phận phần mềm bật lại ô này trên phiếu lương.

**Lưu ý phân biệt:** “Thu nhập **chịu** thuế” (chưa trừ bảo hiểm và giảm trừ gia cảnh) là số **KHÁC** với “Thu nhập **tính** thuế”. Số này hệ thống có tính nhưng **chưa bao giờ được đưa lên phiếu lương** — đây không phải khối bị tắt, mà là chưa từng làm.

**Dễ sai chỗ nào**

1. Thu nhập chịu thuế tính trên tổng thu **TRƯỚC** phạt, còn cột tổng thu lưu lại là **SAU** phạt ⇒ **thu nhập chịu thuế có thể LỚN HƠN tổng thu**. Không phải lỗi.
2. Tiền phạt, tạm ứng, lương đợt 1, khoản danh mục loại Trừ **không giảm** thu nhập chịu thuế. (Đoàn phí thì **có** — nhưng giảm ở bước *thu nhập TÍNH thuế* ở mục 9.3, không phải ở bước này.)
3. Khoản danh mục dùng **bản sao đã ghim trên dòng lương**, không đọc danh mục sống ⇒ đổi ô tích chịu thuế hôm nay **không sửa số của kỳ cũ** (cố ý). Ngược lại, sửa ô tích rồi mà chưa bấm “↻ Tính lại” thì kỳ hiện tại vẫn giữ cách tính cũ.
4. Muốn có hai số “Thu nhập tính thuế TNCN” và “Thu nhập miễn thuế” để đối chiếu quyết toán mà không mở lại được ô trên phiếu ⇒ **phải tính tay** theo công thức ở mục này và mục 9.3.
5. Tổng của “chịu thuế + miễn thuế” có thể lệch tối đa 1 đồng so với tổng thu do làm tròn ở chỗ khác nhau.

## 9.2. Giảm trừ gia cảnh

| Khoản | Mức áp dụng | Khai ở |
|---|---|---|
| Bản thân | **15.500.000 đ/tháng** | Cấu hình lương → Bảo hiểm & Thuế, ô “Giảm trừ bản thân” |
| Mỗi người phụ thuộc | **6.200.000 đ/tháng** | ô “Giảm trừ mỗi người phụ thuộc” |

> Giảm trừ = (giảm trừ bản thân, nếu ô tích “Áp dụng giảm trừ bản thân” đang bật) + giảm trừ mỗi người phụ thuộc × số người phụ thuộc.

**CHỈ áp cho chế độ luỹ tiến.** Hai chế độ “khấu trừ 10%” và “cam kết 08” **không có giảm trừ nào**.

**Khi nào KHÔNG có**
Ô tích “Áp dụng giảm trừ bản thân” tắt ⇒ mất phần giảm trừ bản thân (dành cho người làm hai nơi, chỉ đăng ký ở một nơi). Giảm trừ **người phụ thuộc không phụ thuộc ô tích này**.

> ### ⚠️ HAI Ô NÀY HIỆN KHÔNG CÒN TRÊN MÀN HÌNH — KHÔNG SỬA ĐƯỢC
>
> Ô chọn **“Cách tính thuế TNCN”** và ô tích **“Áp dụng giảm trừ bản thân”** đã bị **tắt hiển thị từ ngày 03/08/2026**. Màn **Hồ sơ nhân viên** chỉ còn hiện để **XEM**, kèm câu hướng dẫn “Đổi ở Lương → Lương nhân viên → Sửa lương” — **nhưng vào tới đó thì không thấy ô nào cả**.
>
> ⇒ **Hiện KHÔNG đổi được cách tính thuế và KHÔNG bỏ tích giảm trừ bản thân cho bất kỳ ai.**
>
> **Đây là việc phải báo bộ phận phần mềm mở lại.** Trong lúc chờ, hai nhóm sau **đang bị tính sai thuế**, kế toán phải **tính tay và theo dõi ngoài sổ để sau này điều chỉnh**:
>
> 1. **Lao động thời vụ / hợp đồng dưới 3 tháng / thực tập** — đang bị tính theo biểu luỹ tiến và **được giảm trừ 15.500.000 đ lẽ ra không có** ⇒ khấu trừ thiếu thuế. Số đúng phải là **10% trên thu nhập chịu thuế** (mục 9.5).
> 2. **Người làm hai nơi** — đang được **giảm trừ bản thân trùng** ở cả hai nơi vì không bỏ tích được.
>
> Với hai nhóm này: tự tính số thuế đúng ngoài hệ thống, ghi vào sổ theo dõi riêng theo từng người từng tháng, chờ mở lại ô rồi điều chỉnh một lần.

**Dễ sai chỗ nào**

1. **Hệ thống không kiểm tra hồ sơ đăng ký người phụ thuộc** — gõ bao nhiêu thì giảm trừ bấy nhiêu. Chứng từ do kế toán tự giữ.
2. Giảm trừ tính **đủ tháng**, không chia theo số ngày làm hay số công.
3. Khi sửa một ô rồi lưu, ô tích “Áp dụng giảm trừ bản thân” được đọc theo mức lương **hôm nay**, không theo tháng của kỳ lương ⇒ **sửa dòng của kỳ CŨ có thể ăn phải trạng thái mới**.

## 9.3. Thu nhập TÍNH thuế — chế độ luỹ tiến

> **Thu nhập tính thuế = Thu nhập chịu thuế − Tiền bảo hiểm − ĐOÀN PHÍ CÔNG ĐOÀN − Giảm trừ gia cảnh**, chặn sàn 0.

⚠️ **Vế “đoàn phí” thêm từ 12/08/2026**, cho khớp bảng lương công ty đang dùng: khối *Các khoản giảm trừ* gồm Bản thân + Người phụ thuộc + BH bắt buộc + **Đoàn phí công đoàn**, rồi *Thu nhập tính thuế* = *Thu nhập chịu thuế* trừ đúng khối đó.

**Tiền bảo hiểm bằng 0 ở 3 nhánh:** thử việc (chạy trước cả hai nhánh kia), bảo hiểm đóng nơi khác, nghỉ không lương từ ngưỡng trở lên. Ba nhóm này **thu nhập tính thuế cao lên tương ứng**.

**Dễ sai chỗ nào** — **CHỊU thuế khác TÍNH thuế.** Chủ hỏi “tổng lương chịu thuế” là số **trước** giảm trừ. Số dùng để tra biểu thuế là **thu nhập tính thuế** — **sau** khi trừ bảo hiểm, **đoàn phí** và giảm trừ gia cảnh. Chặn sàn 0, **âm bao nhiêu cũng không chuyển lỗ sang tháng sau**.

## 9.4. BẢNG TRA BIỂU THUẾ LUỸ TIẾN — 5 BẬC (biểu THÁNG)

| Bậc | Thu nhập TÍNH thuế / tháng | Thuế suất |
|---|---|---|
| 1 | Đến 10.000.000 đ | **5%** |
| 2 | Trên 10.000.000 đến 30.000.000 đ | **10%** |
| 3 | Trên 30.000.000 đến 60.000.000 đ | **20%** |
| 4 | Trên 60.000.000 đến 100.000.000 đ | **30%** |
| 5 | Trên 100.000.000 đ | **35%** |

**Cách cộng: CỘNG TỪNG BẬC, KHÔNG dùng biểu rút gọn.**
Lấy phần thu nhập rơi vào từng bậc nhân thuế suất của bậc đó rồi cộng lại.

*Ví dụ 45.000.000:* 10 triệu × 5% + 20 triệu × 10% + 15 triệu × 20% = 500.000 + 2.000.000 + 3.000.000 = **5.500.000 đ**.

**Số lấy ở đâu**
**Lương → Cấu hình lương → Bảo hiểm & Thuế**, bảng “Bậc / Thu nhập tính thuế đến / Thuế suất”.

**Dễ sai chỗ nào**

1. Xoá **bớt** vài bậc thì không mọc lại; xoá **sạch** thì 5 bậc trên **tự tái sinh** ở lần tính lương hoặc lần mở màn kế tiếp.
2. **Màn sửa bậc thuế không kiểm tra gì cả** — sửa thuế suất thành **số âm vẫn lưu được**.
3. **Không kiểm tra trần bậc phải tăng dần**: nhập lệch thứ tự sẽ làm phép trừ ra âm và **trừ bớt tiền thuế**. Sửa xong bảng thuế thì **đọc lại từ trên xuống**, số ở cột “Thu nhập tính thuế đến” phải tăng dần.
4. Nếu bậc cuối có điền trần thì phần thu nhập vượt trần bậc cuối **không bị đánh thuế đồng nào**. Bậc cuối phải để trống.
5. Đây là **biểu THÁNG**. **Hệ thống chưa làm quyết toán năm**: không cộng dồn 12 tháng, không xử lý người vào hoặc nghỉ giữa năm. **Quyết toán năm phải tính tay.**

## 9.5. BA CHẾ ĐỘ THUẾ

| Chế độ | Áp cho | Cách tính | Có giảm trừ? | Có trừ bảo hiểm? |
|---|---|---|---|---|
| **Luỹ tiến** (mặc định) | Nhân viên chính thức | Biểu 5 bậc ở 9.4 | **CÓ** | **CÓ** |
| **Khấu trừ 10%** | Hợp đồng dưới 3 tháng, thời vụ, thực tập | 10% × thu nhập chịu thuế, nếu thu nhập chịu thuế ≥ 2.000.000; dưới ngưỡng thì 0 | **KHÔNG** | **KHÔNG** |
| **Cam kết 08** | Người đã làm cam kết | Thuế = 0 | — | — |

**Cả ba chế độ đều được miễn đủ 5 khoản ở mục 9.1.**

> ⚠️ **Hiện KHÔNG chuyển được người nào sang chế độ khác** — ô chọn “Cách tính thuế TNCN” đang bị ẩn (mục 9.2). Mọi người đang chạy theo **chế độ đang lưu sẵn trong hồ sơ**, và người mới nhập thì chạy **luỹ tiến**. Ai lẽ ra phải ở “Khấu trừ 10%” hoặc “Cam kết 08” thì **tính tay ngoài sổ**, đồng thời **báo bộ phận phần mềm mở lại ô này**.

**Dễ sai chỗ nào — chế độ “khấu trừ 10%”**

1. Ngưỡng so với **tổng thu nhập chịu thuế của cả dòng lương tháng**, không phải “mỗi lần trả”. Trả 2 đợt trong tháng vẫn tính một lần trên tổng.
2. Vượt ngưỡng thì đánh 10% **toàn bộ**, không chỉ phần vượt. Đúng bằng 2.000.000 là đã bị khấu trừ.
3. Vẫn bị trừ bảo hiểm ở thực nhận nhưng **bảo hiểm không giảm được số thuế**.
4. **Người thử việc KHÔNG tự động vào chế độ này** — trước đây phải khai chế độ thuế trên hồ sơ, **nhưng hiện ô khai đang bị ẩn** ⇒ những người này đang bị tính luỹ tiến, **phải tính tay** (xem cảnh báo ở mục 9.2).
5. Khai thuế suất bằng 0 ⇒ thuế 0 **âm thầm**. Khai ngưỡng bằng 0 ⇒ khấu trừ 10% **từ đồng đầu tiên**.

**Dễ sai chỗ nào — chế độ “cam kết 08”**

1. Thu nhập **tính** thuế trả 0 nhưng thu nhập **chịu** thuế **vẫn đầy đủ** ⇒ **báo cáo quyết toán phải lấy thu nhập CHỊU thuế**; lấy số tính thuế là ra 0, sai bét.
2. Hệ thống **không kiểm tra** điều kiện hợp lệ (mã số thuế, một nơi làm việc, tổng năm dưới ngưỡng) và **không cảnh báo** khi vượt ngưỡng giữa năm. Bật ô tích là miễn vô điều kiện.
3. **Không có hạn hiệu lực theo năm** — bật một lần thì năm sau vẫn miễn. Đầu năm phải **kiểm lại tay**.

## 9.6. Ghi đè thuế bằng tay

**Trên cửa sổ Sửa lương hiện KHÔNG có ô nhập thuế** — dòng tóm tắt ghi rõ “Thuế TNCN … (tự tính theo biểu thuế lũy tiến, không sửa)”.

Tuy vậy **các dòng lương của kỳ CŨ có thể đang ở trạng thái khoá tay thuế**. Với những dòng đó:

| Thao tác | Kết quả |
|---|---|
| Bấm **“↻ Tính lại”** | Dòng đang khoá tay thuế ⇒ **giữ nguyên số thuế cũ**, không tính lại |
| Sửa một ô rồi lưu | Số thuế khoá tay vẫn giữ, nhưng **trần phạt lại dùng số thuế tay** (xem Phần 14, lỗi số 2) |

**Dễ sai chỗ nào**

1. Khi thuế đang khoá tay, cột thu nhập tính thuế **vẫn ghi số tự tính** ⇒ hai số không khớp nhau. **Đừng dùng thu nhập tính thuế để kiểm ngược số thuế đang khoá tay.**
2. Dòng của các kỳ cũ có thuế lớn hơn 0 mặc định **bị đánh dấu khoá tay** — tính lại không đổi số.

---

# 10. PHẠT KỶ LUẬT & TRẦN KHẤU TRỪ 30%

## 10.1. Tổng phạt thô

> **Tổng phạt thô = Giảm trừ khác + Đi trễ / nghỉ KP + Điện thoại vượt trội + Phạt biên bản + Đồng phục / phạt 5S**
>
> **Không gồm**: trừ lỗi hàng khoán (khoản này không cộng vào tổng phạt thô, nhưng **ăn trước vào khoảng còn được trừ** ở mục 10.4), khoản trừ danh mục, tạm ứng.

**Số lấy ở đâu**
Cửa sổ **Sửa lương**, khối **“Các khoản giảm trừ (phạt)”**: **“Giảm trừ khác (trừ)”** · “Đi trễ / nghỉ KP” · “Điện thoại vượt trội” · “Phạt biên bản” · “Đồng phục / phạt 5S”. Hệ thống **chặn số âm** ở cả 5 ô. **Tất cả lưu SỐ THÔ** — số đã nhập, không lưu số đã bị kẹp trần.

**Dễ sai chỗ nào — TÊN CỘT ĐÁNH LỪA**

| Ô / cột | Thực chất |
|---|---|
| **“Giảm trừ khác (trừ)”** | Chính là cột **“Vi phạm”** trên bảng lương và trên file Excel, và là dòng **“Giảm trừ khác”** trên phiếu lương — **một khoản, bốn tên** (mục 4.5) |
| **“Điện thoại vượt trội”** | Thu hồi cước điện thoại vượt định mức — **nhưng bị xếp chung rổ phạt kỷ luật và ăn vào trần 30%** |
| **“Trả đồng phục”** (trên phiếu lương) | Khoản **THU**, cộng vào lương — **không** phải trừ |
| **“Đồng phục / phạt 5S”** | Khoản **PHẠT** — rất dễ nhầm với dòng trên |

Cột phạt lưu số thô nên **nhìn phiếu thấy phạt 100 triệu mà thực trừ chỉ vài triệu** là do trần.

## 10.2. Phạt đi trễ / về sớm tự động

**Tính thế nào**

> Với mỗi ngày **có chấm công**, không phải ngày lễ, không phải ngày “Nghỉ 1×”, không có đơn phép nguyên ngày:
>
> Phút trễ = Giờ vào − (Giờ bắt đầu ca + **dung sai của ca**), không âm. ← **CÓ dung sai**
> Phút về sớm = Giờ kết thúc ca − Giờ ra, không âm. ← **KHÔNG có dung sai**
> Phút vi phạm = Phút trễ + Phút về sớm − Số phút đã xin trên phiếu đã duyệt, không âm.
>
> **Nếu ngày đó là ngày nghỉ theo lịch ⇒ NHÂN ĐÔI SỐ PHÚT trước khi tra bảng.**
>
> Phạt đi trễ = tổng tiền tra bảng bậc của từng ngày.

**Số lấy ở đâu**
Dung sai: ô **“Dung sai đi muộn (phút)”** của từng ca ở **Khai ca → Ca làm việc** (mặc định 5 phút).
Bảng bậc: **Cấu hình lương → Bảo hiểm & Thuế**, bảng **“khấu trừ đi trễ / về sớm”**.
Số phút đã xin: phiếu ở **Chấm công → Đi muộn / về sớm / nghỉ nửa buổi**, trạng thái Đã duyệt.

**Khi nào KHÔNG có**
Chỉ chạy tự động khi ô **“Đi trễ / nghỉ KP”** đang mang nhãn **“tự động”**. Bấm link **“✎ Sửa tay”** để gõ số ⇒ ô chuyển sang nhãn **“đã sửa tay”** và **“↻ Tính lại” sẽ không đè lên nữa**. Bấm **“↩ Về tự động từ chấm công”** để trả về tự tính.

## 10.3. BẢNG TRA BẬC PHẠT ĐI TRỄ / VỀ SỚM

Bảng bậc nằm ở: **Lương → tab “Cấu hình lương” → sub-tab “Bảo hiểm & Thuế” → thẻ “khấu trừ đi trễ / về sớm”** (cột “Đến phút (∞ = trên hết)” và “Số tiền / lần”).

> ### BẢNG TRỐNG KHÔNG CÓ NGHĨA LÀ KHÔNG PHẠT
>
> Hệ thống mới bàn giao chưa có bậc nào. Nhưng **ngay lần đầu bảng được dùng tới, máy TỰ ĐIỀN 4 bậc mặc định và LƯU LẠI thật** (không phải hiển thị tạm), rồi tính tiền phạt bằng đúng 4 bậc đó. **Kỳ lương đầu tiên chạy trên hệ thống “bảng trống” vẫn ra tiền phạt thật, KHÔNG phải 0 đồng.**
>
> **Ba việc sau đều làm bảng tự điền, việc nào tới trước thì tính từ đó:**
> 1. **Mở tab “Cấu hình lương”** — nạp ngay khi tab vừa mở, **chưa cần bấm nút nào**, chưa cần vào sub-tab.
> 2. Bấm nút **“↻ Tính lại”** trên Bảng lương của kỳ nháp.
> 3. Trong cửa sổ **“Sửa lương”**, chuyển ô **“Đi trễ”** từ nhập tay về chế độ tự động.

**Bốn bậc mặc định — tiền cho MỘT ngày vi phạm:**

| Bậc | Số phút vi phạm trong NGÀY | Tiền phạt / NGÀY |
|---|---|---|
| 1 | Đến 15 phút | **20.000 đ** |
| 2 | Trên 15 đến 30 phút | **40.000 đ** |
| 3 | Trên 30 đến 60 phút | **100.000 đ** |
| 4 | Trên 60 phút (ô “Đến phút” để trống = trên hết) | **150.000 đ** |

Tra **bậc đầu tiên** có mốc phút lớn hơn hoặc bằng số phút vi phạm; hết bậc thì lấy bậc cuối.

**Cách tính: MỘT LẦN CHO MỘT NGÀY, KHÔNG nhân theo số phút.**
Mỗi ngày vi phạm không phép, máy cộng số phút đi trễ và số phút về sớm của ngày đó (đã trừ dung sai ca, đã trừ phần có đơn xin nghỉ giờ được duyệt; nếu là ngày nghỉ tuần / Chủ nhật thì số phút **nhân đôi trước khi tra bảng**), tra ra **đúng một mức tiền** cho ngày đó, rồi cộng dồn các ngày trong tháng.

*Ví dụ:* trễ 10 phút trong 3 ngày = 3 × 20.000 = **60.000 đ** (không phải 30 phút × đơn giá). Trễ 10 phút **và** về sớm 10 phút trong **cùng một ngày** = gộp 20 phút = **1 lần 40.000 đ**, không phải hai lần.
Ngày có **đơn phép đã duyệt** và **ngày lễ có lương**: không phạt.

**Dễ sai chỗ nào**

| # | Điều kiện | Hệ quả |
|---|---|---|
| 1 | **Bất đối xứng dung sai** — vào trễ được trừ dung sai ca (5 phút), về sớm **không có dung sai nào** | **Vào trễ 5 phút = 0 đ, nhưng về sớm 5 phút = 20.000 đ** |
| 2 | “Ngày nhân đôi” **không phải riêng Chủ nhật** — là **mọi ngày không phải ngày làm việc theo lịch** | Xưởng nghỉ thứ Bảy thì thứ Bảy cũng nhân đôi phút |
| 3 | **Quên chấm RA** ⇒ phút về sớm = 0 | Ngày treo chỉ bị phạt phần đi trễ, **không** bị phạt về sớm, dù công bằng 0 |
| 4 | Chỉ chạy cho ngày **có dữ liệu chấm công** | Ngày vắng trắng **không sinh phạt trễ** |
| 5 | Ngày nghỉ **nhân đôi PHÚT chứ không nhân đôi TIỀN** | Trễ 20 phút ngày thường = 40.000 đ; cùng 20 phút vào ngày nghỉ → 40 phút → **100.000 đ** |
| 6 | Phạt theo **lần / ngày** | Trễ 5 phút × 10 ngày = **200.000 đ**; trễ 50 phút × 1 ngày = **100.000 đ** |
| 7 | **XOÁ SẠCH 4 BẬC KHÔNG TẮT ĐƯỢC PHẠT** | Lần mở tab Cấu hình lương hoặc lần bấm “↻ Tính lại” kế tiếp, **4 bậc mặc định tự quay lại**. Muốn không phạt thì **để lại bậc và sửa số tiền về 0** |
| 8 | Đổi mức phạt | Sửa số tiền trong bảng → **Lưu** → vào kỳ lương **nháp** bấm “↻ Tính lại” thì số mới mới áp. **Kỳ đã chốt / đã chi giữ nguyên số cũ** |
| 9 | Ô “Đi trễ” đã bị gõ tay đè lên | Ô bị khoá, “↻ Tính lại” không đè nữa — muốn máy tính lại thì bấm **“↩ Về tự động từ chấm công”** |

## 10.4. Trần khấu trừ kỷ luật 30%

**Tính thế nào**

> Gốc tính trần = TỔNG THU (trước phạt) − Tiền bảo hiểm của người lao động − Thuế thu nhập cá nhân, không âm.
> **Khoảng còn được trừ = Tỷ lệ trần × Gốc tính trần − Trừ lỗi hàng khoán**, không âm.
> **Phạt hiệu lực = min(Tổng phạt thô, Khoảng còn được trừ).**
> **TỔNG THU SAU PHẠT = TỔNG THU − Phạt hiệu lực**, chặn sàn 0.
>
> Nếu tỷ lệ trần khai bằng 0 hoặc nhỏ hơn ⇒ **TẮT TRẦN**: phạt hiệu lực = tổng phạt thô.

**Số lấy ở đâu**
Ô **“Trần khấu trừ kỷ luật”** ở tab **Bảo hiểm & Thuế** (mặc định 30% — đây là mức luật theo Điều 102 Bộ luật Lao động, không phải chính sách công ty).

**CHỈ kẹp:** 5 cột phạt kỷ luật (Giảm trừ khác · Đi trễ / nghỉ KP · Điện thoại vượt trội · Phạt biên bản · Đồng phục / phạt 5S) và trừ lỗi hàng khoán — **tất cả chung MỘT trần**.
**KHÔNG kẹp:** khoản trừ danh mục, tạm ứng, lương đợt 1, bảo hiểm, thuế, đoàn phí, điều chỉnh lương.

**Dễ sai chỗ nào**

1. Trần tính trên tổng thu **trước phạt và trước đoàn phí** — không phải trên số còn lại.
2. **Trừ lỗi hàng khoán ăn trước vào khoảng còn được trừ**: trừ lỗi nhiều thì khoảng còn ít, phạt kỷ luật bị cắt gần hết **mà bảng lương không hiện lý do**.
3. Tỷ lệ trần bằng 0 nghĩa là **TẮT TRẦN**, **không** phải cấm trừ.

## 10.5. Phần phạt vượt trần — **hệ thống chưa làm phần theo dõi, phải làm tay**

> Phần vượt = Tổng phạt thô − Phạt hiệu lực ⇒ **BỎ, không chuyển sang kỳ sau.**
>
> **Không có chỗ nào lưu phần vượt. Không có sổ nợ phạt.**

Muốn thu tiếp tháng sau thì nhân sự **phải tự ghi ra ngoài rồi tự gõ lại** vào ô phạt của kỳ sau — hệ thống không nhắc, không theo dõi. Vì cột phạt lưu **số thô** và được **giữ nguyên** khi bấm “↻ Tính lại”, **rất dễ thu trùng** nếu lại gõ thêm lên số cũ.

## 10.6. Trừ lỗi hàng khoán

> Tiền khoán vào tổng thu đã **trừ lỗi ngay từng phiếu** (chặn sàn 0 từng phiếu).
> Nhưng khi tính trần 30%, **tổng trừ lỗi được lấy nguyên, không kẹp**, và **ăn trước** vào khoảng còn được trừ.
>
> ⇒ Trừ lỗi **không bị trừ lần thứ hai** ở bảng lương; nó chỉ **ăn bớt khoảng trần 30%**.

**Dễ sai chỗ nào** — Vì khoán có sàn 0 từng phiếu còn trừ lỗi thì không kẹp, phần “đã bỏ đi” vẫn ăn khoảng trần, **cắt oan phạt kỷ luật hợp lệ**. Hiện tại cả hai luôn rỗng (phần khai sản lượng chưa dùng được) nên trần 30% chưa bao giờ bị bào mòn vì lý do này.

---

# 11. TẠM ỨNG · LƯƠNG ĐỢT 1 · KHOẢN TRỪ DANH MỤC · THỰC NHẬN

## 11.1. Tạm ứng và Lương đợt 1

**Tính thế nào**

> Tạm ứng = tổng số tiền các phiếu loại **“Tạm ứng”**, trạng thái **Đã duyệt**, khai đúng **kỳ ghi trên phiếu**.
> Lương đợt 1 = tổng số tiền các phiếu loại **“Lương đợt 1”**, trạng thái **Đã duyệt**, đúng kỳ.
>
> Cả hai **trừ thẳng vào thực nhận**, **không** vào trần 30%, **không** ảnh hưởng thuế và bảo hiểm.

**Số lấy ở đâu**
**Lương → tab “Tạm ứng”**. Nhãn “Đã duyệt: …đ” ở đầu tab là số đang được tính.

### Ô “Lương trả 1 lần (đợt 1)” ở màn Thiết lập lương — CHỈ LÀ SỐ ĐIỀN SẴN

**Khai số vào ô này KHÔNG trừ vào lương tháng**, không làm thay đổi Tổng thu nhập hay Thực nhận của bất kỳ ai. Coi nó như “mức trả đợt 1 thường dùng” ghi nhớ trong hồ sơ, để lần sau lập phiếu khỏi gõ lại.

Muốn **thật sự trả lương đợt 1 và trừ được vào lương**, phải làm đủ **3 bước**. Thiếu bước nào, tiền cũng **CHƯA bị trừ**:

1. **Lập phiếu.** Vào **Lương → tab “Tạm ứng”** → bấm **“+ Phiếu lương đợt 1”** (nút riêng, **KHÔNG** dùng nút “+ Thêm ứng”) → chọn nhân viên. Ô Số tiền tự điền sẵn đúng bằng con số đã khai trong hồ sơ, sửa lại được nếu tháng này trả khác → **Lưu**. Phiếu sinh ra ở trạng thái *Chờ duyệt*. (Nhân viên cũng có thể tự xin ở tab “Tạm ứng của tôi”, nhưng vẫn phải qua bước duyệt.)
2. **Duyệt phiếu.** Vẫn ở tab Tạm ứng, bấm **“Duyệt”** trên phiếu đó → phiếu chuyển sang *Đã duyệt*. Phiếu để *Chờ duyệt*, bị *Từ chối* hoặc *Hủy* thì hệ thống **không trừ đồng nào**.
3. **Tính lại bảng lương.** Sang **Bảng lương tháng** đúng kỳ ghi trên phiếu → bấm **“↻ Tính lại”**. **ĐÂY MỚI LÀ BƯỚC TIỀN BỊ TRỪ.** Số tiền hiện thành dòng **“Thanh toán lương đợt 1”** ở cột *Đợt 1 / Tạm ứng* và bị trừ khỏi Thực nhận.

**Ba chỗ dễ mất tiền — nhớ kỹ:**

- Duyệt phiếu xong mà **quên bấm “↻ Tính lại”** thì bảng lương vẫn giữ số cũ, nhìn vào tưởng đã trừ nhưng **chưa trừ**.
- Kỳ lương **đã bấm Chốt** thì nút “↻ Tính lại” biến mất. Phải bấm **“Mở lại”** → **“↻ Tính lại”** → **Chốt** lần nữa.
- Phiếu phải ghi **đúng tháng/năm** mới trừ vào kỳ đó. Ghi lệch kỳ là số rơi sang tháng khác.

**Lưu ý về số liệu:** số bị trừ vào lương luôn là số ghi **trên phiếu đã duyệt**, không phải số đang khai trong hồ sơ. Sửa con số ở ô hồ sơ **sau khi** phiếu đã lập thì phiếu cũ **giữ nguyên số của nó** — muốn đổi phải sửa hoặc hủy chính phiếu đó.

**Đối chiếu khi rà sổ:** khoản “Thanh toán lương đợt 1” để **dòng riêng**, **KHÔNG gộp** chung với “Tạm ứng đã nhận” — khi cộng đối chiếu phải lấy **cả hai dòng**.

**Khi nào KHÔNG có**
Chỉ tính phiếu **Đã duyệt**. Phiếu Chờ duyệt / Từ chối / Đã hủy đều không trừ.
**Không còn trần số tiền tạm ứng** — đừng để ai tưởng còn giới hạn 10%.

**Dễ sai chỗ nào**

1. Phiếu ứng **khai nhầm kỳ** ⇒ tiền đã đưa nhưng lương **không trừ** — **không có cảnh báo nào**.
2. Duyệt phiếu **sau khi** đã bấm “↻ Tính lại” ⇒ chưa trừ, cho tới lần tính lại kế tiếp. **Sửa một ô rồi lưu dùng lại số đã lưu, không đọc lại phiếu mới duyệt.**
3. Chiều ngược lại: hủy một phiếu đã duyệt vẫn được, nhưng hủy xong mà chỉ sửa một ô thì **số cũ vẫn bị trừ** — phải bấm “↻ Tính lại” mới hoàn lại.
4. Ứng vượt lương: **sàn 0 nuốt phần dư**, hệ thống **không ghi nợ ở đâu**. Muốn thu tiếp phải nhớ tay.

## 11.2. Khoản trừ theo danh mục

**Tính thế nào**

> Khoản trừ = tổng mọi khoản danh mục loại **“Trừ”**, gộp **cả hai nguồn**: gán ở hồ sơ nhân viên và phát sinh riêng của kỳ.
> **Trừ thẳng vào thực nhận. Không vào trần 30%. Không giảm thu nhập chịu thuế.**

Đây là **khấu trừ thoả thuận** (mua đồng phục, trừ tiền cơm, thu hộ…), cố ý tách khỏi rổ kỷ luật.

**Số lấy ở đâu**
Loại khoản (Thu / Trừ) khai ở **Cấu hình lương → Danh mục khoản thu nhập**. Số tiền gán ở **Thiết lập lương** hoặc **Sửa lương → Khoản phát sinh tháng này**.

**Dễ sai chỗ nào**

1. Phiếu lương **có in từng dòng khấu trừ danh mục**. Nhưng **Bảng lương tháng không có cột tổng khấu trừ danh mục** ⇒ cộng ngang bảng lương không ra thực lĩnh.
2. **Cột “Trừ” trên phiếu lương cộng các khoản phạt theo SỐ THÔ** ⇒ **tổng cột “TỔNG TRỪ” không khớp với (TỔNG THU − THỰC NHẬN)** khi phạt bị kẹp trần. Chỗ này phải giải thích được cho người lao động.
3. Phía thu: khoản gán ở hồ sơ **đã nằm trong cột Phụ cấp**, khoản phát sinh cộng riêng — **nối hai danh sách lại là cộng hai lần**.

## 11.3. THỰC NHẬN

> **TỔNG THU SAU PHẠT = TỔNG THU − Phạt hiệu lực**, chặn sàn 0 *(lần một)*
>
> **THỰC NHẬN = TỔNG THU SAU PHẠT − Bảo hiểm − Đoàn phí − Thuế TNCN − Tạm ứng − Lương đợt 1 − Khoản trừ danh mục**, chặn sàn 0 *(lần hai)*

> **Đếm cho đúng: sau tổng thu có ĐÚNG 6 khoản trừ, không khoản nào bị kẹp trần**: bảo hiểm · đoàn phí · thuế · tạm ứng · lương đợt 1 · khoản trừ danh mục.
>
> **Các khoản PHẠT không nằm trong 6 khoản này** — chúng đã bị trừ sớm hơn một bước (ở “TỔNG THU SAU PHẠT”) và **có bị kẹp trần 30%**. Ô **“Giảm trừ khác (trừ)”** thuộc nhóm phạt đó, **không** thuộc 6 khoản trên.
>
> **“Điều chỉnh lương” không phải khoản trừ nào cả** — nó là khoản **THU**, cộng theo dấu vào tổng thu trước phạt (mục 4.5).

**Dễ sai chỗ nào** — **Hai lần chặn sàn 0 che mất tiền**: nếu tổng khấu trừ lớn hơn tổng thu thì phần thiếu **biến mất**, không ghi nợ, không chuyển kỳ sau, phiếu lương chỉ hiện 0 đồng. **Phải kiểm tay và ghi ra ngoài trước khi giải thích với người lao động.**

---

# 12. HAI VÍ DỤ SỐ CHẠY TRỌN VẸN

## VÍ DỤ 1 — Công nhân sản xuất có tăng ca

**Hồ sơ**

| Mục | Giá trị |
|---|---|
| Nhân viên | Nguyễn Văn Bình — Thợ in offset, tổ In offset |
| Trạng thái | **Chính thức** |
| Kỳ lương | **08/2026** · Công chuẩn theo lịch = **26** |
| Tổ | Lương khoán: **TẮT** · Tăng ca: **BẬT** · Chuyên cần: **BẬT** |
| Lương cơ bản (đóng BH) | 7.800.000 · Lương trách nhiệm 0 ⇒ **mức nền 7.800.000** |
| Thưởng chuyên cần | 300.000 |
| Phụ cấp thâm niên | 200.000 |
| Khoản danh mục ở hồ sơ | Hỗ trợ đi lại 300.000 (**Miễn thuế**) |
| Người phụ thuộc | 0 · Đoàn viên: **CÓ**, tỷ lệ đoàn phí 0,5% |
| Ca làm | Ca ngày (không qua đêm) · Phụ cấp cơm 25.000 đ/ngày · Phụ cấp ca 0 |

**Chấm công**

| Mục | Số |
|---|---|
| Ngày thường đủ công | 24 |
| Ngày thường có đi trễ 20 phút | 2 ngày × 0,96 công = 1,92 |
| Đi làm thêm 1 Chủ nhật | 1,0 công |
| **Công thực** | **26,92** |
| Nghỉ phép có lương | 0 |
| Tăng ca ngày thường (có phiếu duyệt phủ đủ) | **20 giờ** |
| Trong đó rơi vào 22h–06h | **6 giờ** |
| Đi trễ | 2 ngày, mỗi ngày trễ 20 phút (dung sai 5 phút ⇒ 15 phút vi phạm/ngày) |
| Tạm ứng đã duyệt đúng kỳ | 2.000.000 |

> **Vì sao công thực là 26,92 chứ không phải 27,0:** ngày nào đi trễ thì công của ngày đó tính
> theo số phút làm thật, nên hai ngày trễ 20 phút mỗi ngày chỉ được 0,96 công. Con số lẻ này
> **không làm đổi một đồng nào** trong ví dụ (lương công đã chạm trần 26 công, chuyên cần vẫn đủ,
> cơm ca vẫn 27 suất vì ngày nào cũng trên nửa công) — nhưng để nguyên 27,0 thì kế toán tự bấm
> lại sẽ ra số khác và tưởng máy sai.

### Bước 1 — Đơn giá

| Chỉ tiêu | Cách tính | Kết quả |
|---|---|---|
| Mức nền hiệu lực | 7.800.000 × 1,0 | 7.800.000 |
| **Đơn giá ngày** | 7.800.000 ÷ 26 | **300.000 đ/công** |
| **Đơn giá giờ** | 300.000 ÷ 8 | **37.500 đ/giờ** |

### Bước 2 — Lương theo công

Công phép 0 · Công đi làm 26,92 · Công đi làm được trả = min(26,92 ; 26) = **26,0** ← trần cắt phần dôi
**Lương theo công = 300.000 × 26,0 = 7.800.000**

> 1 công Chủ nhật dôi ra **không** ra thêm tiền ở đây; nó được trả ở bước 4.

### Bước 3 — Chuyên cần và Phụ cấp

Số ngày nghỉ = 26 − 26,92 → không âm → **0** ⇒ tỷ lệ 100% ⇒ **Chuyên cần = 300.000**
**Phụ cấp = 0 + 200.000 (thâm niên) + 300.000 (hỗ trợ đi lại) = 500.000**

### Bước 4 — Tăng ca

| Thành phần | Cách tính | Số tiền |
|---|---|---|
| 20 giờ tăng ca ngày thường | 37.500 × 20 × 1,5 | 1.125.000 |
| Phần cộng thêm làm Chủ nhật | 300.000 × 1,0 × (2,0 − 1) | 300.000 |
| **Cột “Tăng ca”** | | **1.425.000** |

### Bước 5 — Cơm ca và Phụ cấp ca đêm

Cơm ca = 25.000 × 27 ngày đi làm = **675.000**  *(đếm theo SỐ NGÀY có mặt, không theo số công lẻ — hai ngày đi trễ vẫn trên nửa công nên vẫn đủ suất)*
Phụ cấp ca đêm: phần trong ca = 0 (ca ngày, không qua đêm); phần tăng ca đêm = 6 × 37.500 × (30% + 20% × 1,0) = 6 × 37.500 × 0,5 = **112.500**

> Tổng cho 1 giờ tăng ca đêm = 1,5 lần (cột Tăng ca) + 0,5 lần (cột Ca đêm) = **2,0 lần = 200%**.

### Bước 6 — Phiếu lương, cột CÁC KHOẢN THU

| Khoản THU | Số tiền | Cộng dồn |
|---|---|---|
| Lương theo công | 7.800.000 | 7.800.000 |
| Cơm ca | 675.000 | 8.475.000 |
| Phụ cấp ca đêm (giờ × hệ số) | 112.500 | 8.587.500 |
| Phụ cấp thâm niên | 200.000 | 8.787.500 |
| Chuyên cần | 300.000 | 9.087.500 |
| Tăng ca | 1.425.000 | 10.512.500 |
| Hỗ trợ đi lại | 300.000 | 10.812.500 |
| **TỔNG THU** | | **10.812.500** |

> Cột “Phụ cấp” trên Bảng lương tháng = 200.000 + 300.000 = **500.000** (thâm niên + khoản danh mục hồ sơ).

### Bước 7 — Bảo hiểm và Đoàn phí

Ngày nghỉ không lương = 26 − 26,92 − 0 → 0 < 14 ⇒ **đóng bình thường**
Mức đóng bảo hiểm = **7.800.000** (lương cơ bản, không phải mức nền)
Bảo hiểm người lao động = 7.800.000 × 9,5% + 7.800.000 × 1% = 741.000 + 78.000 = **819.000**
Đoàn phí = 7.800.000 × 0,5% = **39.000**

Ba dòng trên phiếu: BHXH 624.000 · BHYT 117.000 · BHTN = 819.000 − 624.000 − 117.000 = **78.000** ✓

### Bước 8 — Thuế thu nhập cá nhân

Thu nhập miễn thuế = 1.425.000 (tăng ca) + 112.500 (ca đêm) + 300.000 (hỗ trợ đi lại) + 675.000 (cơm ca) = **2.512.500**
Thu nhập chịu thuế = 10.812.500 − 2.512.500 = **8.300.000**
Giảm trừ = 15.500.000
Thu nhập tính thuế = 8.300.000 − 819.000 − 15.500.000 = số âm ⇒ **0**
**THUẾ = 0**

> Hai số “Thu nhập miễn thuế 2.512.500” và “Thu nhập tính thuế 0” **hiện không in trên phiếu lương** (mục 9.1) — muốn có thì tính tay như trên.

### Bước 9 — Phạt và trần 30%

Phạt đi trễ = 2 ngày × bậc 1 (15 phút ≤ 15) × 20.000 = **40.000**
Gốc tính trần = 10.812.500 − 819.000 − 0 = 9.993.500
Khoảng còn được trừ = 30% × 9.993.500 = 2.998.050
Phạt hiệu lực = min(40.000 ; 2.998.050) = **40.000** ← chưa chạm trần

### Bước 10 — Phiếu lương, cột CÁC KHOẢN TRỪ

| Khoản TRỪ | Số tiền | Cộng dồn |
|---|---|---|
| BHXH (8%) | 624.000 | 624.000 |
| BHYT (1,5%) | 117.000 | 741.000 |
| BHTN (1%) | 78.000 | 819.000 |
| Công đoàn | 39.000 | 858.000 |
| Thuế TNCN | 0 | 858.000 |
| Đi trễ / nghỉ KP | 40.000 | 898.000 |
| Tạm ứng đã nhận | 2.000.000 | 2.898.000 |
| **TỔNG TRỪ** | | **2.898.000** |

### THỰC NHẬN

**10.812.500 − 2.898.000 = 7.914.500 đ**

*Kiểm ngược:* 10.812.500 − 40.000 = 10.772.500 → − 819.000 = 9.953.500 → − 39.000 = 9.914.500 → − 2.000.000 = **7.914.500** ✓

---

## VÍ DỤ 2 — Nhân viên văn phòng lương cao, có người phụ thuộc

**Hồ sơ**

| Mục | Giá trị |
|---|---|
| Nhân viên | Trần Thị Mai — Trưởng phòng Kinh doanh |
| Trạng thái | **Chính thức** |
| Kỳ lương | **02/2026** · Công chuẩn theo lịch = **24** ← *tháng 2 mẫu số nhỏ hơn* |
| Tổ | Không khoán, Tăng ca BẬT (nhưng không có giờ tăng ca) |
| Lương cơ bản (đóng BH) | 36.000.000 · Lương trách nhiệm 12.000.000 ⇒ **mức nền 48.000.000** |
| Thưởng chuyên cần | 500.000 |
| Phụ cấp thâm niên | 500.000 |
| Khoản danh mục ở hồ sơ | Phụ cấp điện thoại 500.000 (**Chịu thuế**) |
| Khoản phát sinh của kỳ | Thưởng doanh số Q1 **10.000.000** (Chịu thuế) |
| Khoản danh mục loại **Trừ** | Trừ tiền đồng phục 400.000 |
| Người phụ thuộc | **2** · Áp dụng giảm trừ bản thân: **CÓ** |
| Đoàn viên | CÓ (0,5%) |
| Ca làm | Hành chính · Phụ cấp cơm 25.000 đ/ngày · Phụ cấp ca 0 |

**Chấm công**

| Mục | Số |
|---|---|
| Đi làm đủ công | 21 ngày |
| Nghỉ **phép năm có lương** | 2 ngày |
| Nghỉ **không lương** | 1 ngày |
| **Công thực** | **23,0** (21 + 2) |
| Công phép có lương | **2,0** |
| Tăng ca / ca đêm / phạt | 0 |
| **Lương đợt 1** (phiếu đã duyệt đúng kỳ, đã tính lại) | 15.000.000 |

### Bước 1 — Đơn giá

| Chỉ tiêu | Cách tính | Kết quả |
|---|---|---|
| Mức nền hiệu lực | 48.000.000 × 1,0 | 48.000.000 |
| **Đơn giá ngày** | 48.000.000 ÷ 24 | **2.000.000 đ/công** |
| **Đơn giá ngày phép** (chỉ theo lương cơ bản) | 36.000.000 ÷ 24 | **1.500.000 đ/công** |

### Bước 2 — Lương theo công (có ngày phép)

Công phép = min(2,0 ; 23,0) = 2,0 · Công đi làm = 23,0 − 2,0 = 21,0
Công đi làm được trả = min(21,0 ; 24) = **21,0**
Công phép được trả = min(2,0 ; 24 − 21,0 = 3,0) = **2,0**

Lương ngày phép = 1.500.000 × 2,0 = **3.000.000**
**Lương theo công = 2.000.000 × 21,0 + 3.000.000 = 45.000.000**

> Dòng “Trong đó: lương ngày phép 3.000.000” là số **NẰM TRONG** 45.000.000 — **không cộng lại**.
> Ngày phép chỉ được 1.500.000/công chứ không phải 2.000.000, vì **phép năm không có lương trách nhiệm**.

### Bước 3 — Chuyên cần và Phụ cấp

Số ngày nghỉ = 24 − (23,0 + 0) = **1,0** ← 1 ngày nghỉ không lương
Tỷ lệ = 1 − 0,5 × 1,0 = 0,5 ⇒ **Chuyên cần = 500.000 × 0,5 = 250.000**
Phụ cấp = 0 + 500.000 (thâm niên) + 500.000 (điện thoại) = **1.000.000**
Khoản phát sinh của kỳ = **10.000.000**

### Bước 4 — Cơm ca

Cơm ca = 25.000 × **21 ngày đi làm** = **525.000**

> 2 ngày nghỉ phép **không có suất cơm ca** — chỉ đếm ngày có đi làm.

### Bước 5 — Phiếu lương, cột CÁC KHOẢN THU

| Khoản THU | Số tiền | Cộng dồn |
|---|---|---|
| Lương theo công *(trong đó lương ngày phép 3.000.000)* | 45.000.000 | 45.000.000 |
| Cơm ca | 525.000 | 45.525.000 |
| Phụ cấp thâm niên | 500.000 | 46.025.000 |
| Chuyên cần | 250.000 | 46.275.000 |
| Phụ cấp điện thoại | 500.000 | 46.775.000 |
| Thưởng doanh số Q1 (khoản phát sinh của kỳ) | 10.000.000 | 56.775.000 |
| **TỔNG THU** | | **56.775.000** |

### Bước 6 — Bảo hiểm và Đoàn phí

Ngày nghỉ không lương = 24 − 23,0 − 0 = 1,0 < 14 ⇒ **đóng bình thường**
Mức đóng bảo hiểm = **36.000.000** ← lương cơ bản, **không phải 48.000.000**
Bảo hiểm = 36.000.000 × 9,5% + 36.000.000 × 1% = 3.420.000 + 360.000 = **3.780.000**
Đoàn phí = 36.000.000 × 0,5% = **180.000** ← tính trên gốc, không kẹp trần

Ba dòng trên phiếu: BHXH 2.880.000 · BHYT 540.000 · BHTN = 3.780.000 − 2.880.000 − 540.000 = **360.000** ✓

### Bước 7 — Thuế thu nhập cá nhân

Thu nhập miễn thuế = 525.000 (cơm ca) — hai khoản danh mục đều **chịu thuế**
Thu nhập chịu thuế = 56.775.000 − 525.000 = **56.250.000**
Giảm trừ = 15.500.000 + 6.200.000 × 2 = **27.900.000**
Thu nhập tính thuế = 56.250.000 − 3.780.000 − 27.900.000 = **24.570.000**

| Bậc | Phần thu nhập rơi vào bậc | Thuế suất | Thuế |
|---|---|---|---|
| 1 | 10.000.000 | 5% | 500.000 |
| 2 | 24.570.000 − 10.000.000 = 14.570.000 | 10% | 1.457.000 |
| 3–5 | 0 | — | 0 |
| | | **CỘNG** | **1.957.000 đ** |

### Bước 8 — Phạt

Tổng phạt thô = 0 ⇒ phạt hiệu lực = 0.

### Bước 9 — Phiếu lương, cột CÁC KHOẢN TRỪ

| Khoản TRỪ | Số tiền | Cộng dồn |
|---|---|---|
| BHXH (8%) | 2.880.000 | 2.880.000 |
| BHYT (1,5%) | 540.000 | 3.420.000 |
| BHTN (1%) | 360.000 | 3.780.000 |
| Công đoàn | 180.000 | 3.960.000 |
| Thuế TNCN | 1.957.000 | 5.917.000 |
| Trừ tiền đồng phục | 400.000 | 6.317.000 |
| Thanh toán lương đợt 1 | 15.000.000 | 21.317.000 |
| **TỔNG TRỪ** | | **21.317.000** |

### THỰC NHẬN ĐỢT 2

**56.775.000 − 21.317.000 = 35.458.000 đ**

*Kiểm ngược:* 56.775.000 − 3.780.000 = 52.995.000 → − 180.000 = 52.815.000 → − 1.957.000 = 50.858.000 → − 15.000.000 = 35.858.000 → − 400.000 = **35.458.000** ✓

**Ba điểm phải giải thích được nếu nhân viên hỏi:**

1. Nghỉ **1 ngày không lương** làm mất **50% chuyên cần** (250.000 đ), không phải mất 1/24.
2. Mức đóng bảo hiểm tính trên **36.000.000** (lương cơ bản), không phải 48.000.000 — nên số bảo hiểm thấp hơn kỳ vọng.
3. 400.000 đ đồng phục hiện thành **một dòng riêng** ở cột TRỪ, không gộpvào dòng nào khác. Riêng 15.000.000 đ lương đợt 1 để **dòng riêng**, không gộp với “Tạm ứng đã nhận”.

---

# 13. NHỮNG CHỖ HỆ THỐNG LÀM KHÁC CÁCH TÍNH TAY

Đây là **quyết định đã chốt**, **không phải lỗi máy**. Kế toán quen tính tay sẽ thấy lệch — đọc cột lý do rồi giải thích cho người lao động, **đừng tự sửa cấu hình**.

| # | Chỗ khác | Cách tính tay quen thuộc / luật | Hệ thống đang làm | Vì sao & rủi ro |
|---|---|---|---|---|
| 1 | **Miễn thuế toàn bộ tiền tăng ca** | ✅ **Đúng luật** — Luật Thuế TNCN 2025 bỏ vế "chỉ miễn phần chênh"; chỉ phần **vượt định mức** mới chịu thuế | Miễn toàn bộ | Không còn rủi ro. Còn thiếu: chưa đếm trần 40 giờ/tháng nên phần vượt vẫn được miễn oan |
| 1b | **Tiền ngày “Nghỉ 1×” nay CHỊU thuế** (sửa 17/08/2026) | Trả đúng 1 lần, không hệ số ⇒ là lương ngày thường | Cộng vào thu nhập chịu thuế | Kế toán chốt: *“lương thuế chỉ 1 công bình thường”*. **Tiền vẫn trả đủ**, chỉ khác ở chỗ khai thuế |
| 2 | **Cơm ca miễn thuế không có trần 730.000 đ/tháng** | Luật cho trần 730.000 đ/tháng | Miễn toàn bộ | Đã chốt. Muốn áp trần phải sửa hệ thống |
| 3 | **Hệ số thử việc 80%** | Luật tối thiểu 85% | Mặc định 80% | Là **số cấu hình** — sửa ở ô “% lương thử việc” |
| 4 | **Mức đóng bảo hiểm không chia theo công** | Nhiều nơi chia theo ngày công thực | Đóng trên **toàn bộ** lương cơ bản dù đi làm 3/26 công | Đúng quy định về thu bảo hiểm |
| 5 | **Mức đóng bảo hiểm chỉ bám lương cơ bản** | Thông lệ: lương + phụ cấp cố định | Chỉ ô “Lương cơ bản (đóng BH)” | Chủ đã chốt: lương cơ bản chính là gốc đóng |
| 6 | **Ngày phép năm chỉ trả lương cơ bản** | Thông lệ: trả nguyên lương như ngày làm | Không có lương trách nhiệm | Đã chốt |
| 7 | **Đoàn phí tính trên gốc chưa kẹp trần bảo hiểm** | Thường bám mức đóng đã kẹp trần | Tính trên nguyên lương cơ bản | Lương 60 triệu: đoàn phí trên 60 triệu, bảo hiểm chỉ trên 50,6 triệu |
| 8 | **Vẫn trừ đoàn phí ở 2 nhánh miễn bảo hiểm** | — | Bảo hiểm 0 nhưng đoàn phí vẫn trừ | Cố ý |
| 9 | **Đoàn phí không giảm thu nhập chịu thuế** | — | Không trừ | Đừng gộp đoàn phí vào phần khấu trừ trước thuế khi đối chiếu quyết toán |
| 10 | **Ngày “Nghỉ 1×” trả trọn 1 lần, không lấp trần** | — | Được trả trọn dù đã đủ công chuẩn | Chủ ý |
| 11 | **Dôi công không ra thêm tiền ở lương công** | Thông lệ: làm Chủ nhật = 200% lương ngày | Chỉ trả phần chênh 1 lần, vì 1 lần cơ bản coi như đã trong lương công — **nhưng lương công đã bị trần cắt** | **Đây là chỗ lệch thật với cách tính tay 200%.** Phải nói trước với thợ |
| 12 | **Cơm ca / phụ cấp ca trọn suất hoặc không** | Có nơi chia theo giờ | Đủ ngưỡng thì trọn suất, dưới ngưỡng thì 0 | Cố ý không nhân tỷ lệ |
| 13 | **Chuyên cần trừ theo bậc nửa ngày = mất 25%** | Nhiều nơi giảm tuyến tính | Nghỉ 2 ngày mất sạch | Chính sách công ty |
| 14 | **Vào trễ có dung sai, về sớm không có** | Thông lệ đối xứng | Về sớm 5 phút = 20.000 đ; vào trễ 5 phút = 0 đ | Bất đối xứng có thật |
| 15 | **Phạt đi trễ tính 1 lần / ngày, không nhân theo phút** | Có nơi tính theo phút | Cộng phút trễ + phút về sớm trong ngày, tra ra **một** mức tiền | Cố ý. Trễ 10 phút × 3 ngày = 60.000 đ, không phải 30 phút gộp |
| 16 | **Có đơn chỉ tha đúng số phút đã xin**, không tha cả ngày | Thông lệ: có đơn là tha | Trừ đúng số phút | Cố ý — nếu không, ai cũng xin 5 phút để thoát phạt |
| 17 | **Có đơn giữ chuyên cần nhưng vẫn mất tiền công** | Thường gộp làm một | Hai thứ tách nhau | Công có đơn chỉ nuôi chuyên cần |
| 18 | **Trừ lỗi khoán ăn vào trần 30% dù đã trừ trong tiền khoán** | — | Không trừ hai lần, nhưng bào mòn trần phạt | Cố ý gộp chung một trần |
| 19 | **Khoản trừ danh mục không vào trần 30%** | — | Trừ thẳng vào thực nhận | Cố ý: đây là khấu trừ **thoả thuận**, không phải kỷ luật |
| 20 | **Phần phạt vượt trần bỏ luôn, không dồn kỳ sau** | Thông lệ: treo nợ | Mất luôn | Không có sổ nợ phạt — phải theo dõi tay |
| 21 | **Hai lần chặn sàn 0** | — | Tiền thiếu biến mất, không ghi nợ | Cố ý, để không in phiếu lương số âm |
| 22 | **Tra mức lương theo ngày cuối tháng** | Thông lệ: chia đôi theo ngày hiệu lực | Cả tháng ăn mức mới | Cố ý cho đơn giản |
| 23 | **Ca đêm phân loại ngày theo NGÀY VÀO CA** | Thông lệ: theo ngày lịch của từng giờ | Ca đêm vào 30/04 kéo sang 01/05 vẫn tính hệ số 30/04 | Cố ý, một công thức cho mọi ca |
| 24 | **“Khấu trừ 10%” so ngưỡng trên TỔNG THÁNG** | Luật diễn đạt “mỗi lần trả” | Trả 2 đợt vẫn tính một lần trên tổng | Đã biết |
| 25 | **“Cam kết 08” miễn vô điều kiện, không hạn năm** | Luật đòi mã số thuế, một nơi làm việc, dưới ngưỡng | Bật ô tích là miễn | **Rủi ro tuân thủ** — không cảnh báo, phải kiểm lại tay đầu năm |
| 26 | **Không có quyết toán năm** | — | Chỉ tính biểu tháng | **Hệ thống chưa làm phần này, quyết toán năm phải tính tay** |
| 27 | **Đầu việc khoán đã ghim vào lệnh thì cố định** | — | Xưởng lên giá sau không xê dịch lệnh đã phát | Cố ý |

---

# 14. CHỖ HAI ĐƯỜNG TÍNH RA HAI SỐ — ĐỪNG TIN SỐ VỪA HIỆN

Khác hẳn Phần 13. Đây là chỗ **bấm “↻ Tính lại” và “sửa một ô rồi lưu” ra hai số khác nhau**, hoặc luật bị áp sai. Gặp những trường hợp này thì **bấm “↻ Tính lại” rồi mới đọc số**.

| # | Lỗi | Xảy ra khi nào | Hậu quả tiền |
|---|---|---|---|
| **1** | **Sửa ô mức tháng rồi lưu thì không nhân hệ số thử việc** | Nhân viên **thử việc** và có người sửa ô mức tháng | Lương theo công **đội lên khoảng +25%** |
| **1b** | **Đơn giá ngày phép bị suy ngược từ số cũ trên dòng** | Sửa mức tháng cho người có ngày phép | Đổi mức tháng **không đổi** đơn giá ngày phép |
| **2** | **Trần phạt 30% dùng HAI số thuế khác nhau** | Thuế đang **khoá tay** **VÀ** phạt chạm trần | “↻ Tính lại” dùng **thuế tự tính**; sửa một ô rồi lưu dùng **thuế tay** ⇒ **cùng một dòng, hai thao tác, ra hai số thực nhận khác nhau** |
| **3** | **Sửa một ô rồi lưu tính lại đoàn phí mà quên kiểm ô tích đoàn viên** | Nhân viên **không phải đoàn viên** và tỷ lệ đoàn phí > 0 | “↻ Tính lại” ra 0 đ; **mọi thao tác trên dòng** (sửa ô, thêm/xoá khoản phát sinh) làm đoàn phí **sống lại** và trừ oan |
| **4** | **Mức đóng bảo hiểm và tiền bảo hiểm bị đóng băng** | Sửa ô “Lương cơ bản (đóng BH)” ở hồ sơ mà không bấm “↻ Tính lại” | Bảng lương **vẫn dùng số cũ** |
| **5** | **Màn sửa bậc thuế không kiểm tra gì** | Sửa bảng biểu thuế | Nhập **thuế suất âm** vẫn lưu; **trần bậc lệch thứ tự** làm thuế cộng sai, có thể ra số âm |
| **6** | **Ba dòng bảo hiểm trên phiếu tính lại theo tham số HIỆN TẠI** | Sửa tỷ lệ hoặc trần bảo hiểm sau khi kỳ đã chốt | Hai dòng đầu đổi số, **sai lệch dồn hết vào dòng BHTN** — có thể ra số vô lý, kể cả **âm** |
| **7** | **Tổ khoán mất tăng ca mà không có khoán bù** | Tổ nào đang bật “Lương khoán / sản lượng” | Tăng ca = 0 (mất cả phần cộng thêm lễ/Chủ nhật và tiền ngày “Nghỉ 1×”) trong khi cột Khoán luôn 0. **Xử lý: TẮT công tắc đó** |
| **8** | **Ô tích làm khoán hở một chiều** | Sửa ô tích ở màn **Phòng ban** | Không ghi gì sang Cấu hình lương ⇒ hai nơi lệch nhau, phải **kiểm lại cả hai màn** |
| **9** | **Thưởng / phạt tổ trưởng theo % hàng lỗi chưa nối** | Khai bậc trên màn hình | **Không ra đồng nào.** Băng cảnh báo đang nói đúng — **đừng gỡ** |
| **10** | **Xoá bảng bậc phạt trễ KHÔNG tắt được phạt** | Có người xoá sạch 4 bậc để “khỏi phạt” | 4 bậc mặc định **tự quay lại** ở lần mở tab Cấu hình lương hoặc lần “↻ Tính lại” kế tiếp ⇒ **vẫn phạt như cũ**. Muốn không phạt thì **giữ bậc, sửa số tiền về 0** |
| **11** | **Ô chọn cách tính thuế và ô tích giảm trừ bản thân bị ẩn** | Mọi trường hợp, từ 03/08/2026 | **Không đổi được cho ai.** Thời vụ / dưới 3 tháng đang được giảm trừ 15.500.000 đ lẽ ra không có; người làm hai nơi đang giảm trừ trùng ⇒ **tính tay, ghi sổ ngoài, báo bộ phận phần mềm mở lại** |
| **12** | **Hai ô thuế trên phiếu lương bị ẩn** | Mọi phiếu lương in ra và màn “Phiếu lương của tôi” | Chỉ **ẩn khỏi mắt**, tiền không đổi. “Thu nhập tính thuế” còn tra được ở màn Sửa lương; **“Thu nhập miễn thuế” hiện không tra được ở đâu** |

> **Nguyên tắc phòng bệnh — nhớ nguyên văn:**
> Hai đường tính **phải ra cùng một số**. Thêm bất kỳ khoản thu hay khoản chi nào vào một đường mà quên đường kia thì **thao tác “sửa một ô” sẽ ăn mất tiền người lao động trong im lặng**, bảng lương vẫn trông bình thường. Bệnh này **đã tái phát 3 lần**.
> ⇒ **Sau mỗi lần sửa ô, bấm “↻ Tính lại” trước khi đọc số và trước khi chốt.**

---

# 15. VIỆC PHẢI KIỂM TRƯỚC KHI CHỐT BẢNG LƯƠNG

Làm theo đúng thứ tự. Tick hết mới được bấm **“🔒 Chốt”**.

### A. Dữ liệu đầu vào

- [ ] Kỳ **chấm công** đã bấm **“Chốt công tháng”** chưa? (Chốt rồi thì màn Lương đọc bản chốt — sửa chấm công sau đó **không đổi số**)
- [ ] Mở **Chấm công → Lịch & Ngày lễ**: tuần làm việc chuẩn, ngày lễ, ngày làm bù, ngày “Nghỉ 1×” đã khai đủ chưa?
- [ ] Số **“NC chuẩn”** trên phiếu lương tháng này bằng bao nhiêu? Có khớp lịch không? (**Khác 26 là bình thường**)
- [ ] Có tổ nào đang bật công tắc **“Lương khoán / sản lượng”** không? ⇒ **Cả tổ đó đang mất tăng ca mà không có khoán bù. Tắt đi.** (Kiểm lại **cả** màn Phòng ban lẫn màn Cấu hình lương — hai nơi có thể lệch)
- [ ] Mở **Cấu hình lương → Bảo hiểm & Thuế**: bảng biểu thuế có đủ 5 bậc, số ở cột “Thu nhập tính thuế đến” **tăng dần**, bậc cuối để trống?
- [ ] Bảng **“khấu trừ đi trễ / về sớm”**: 4 bậc và **số tiền từng bậc** có đúng ý công ty không? (Bảng này **tự điền lại 4 bậc mặc định** nếu bị xoá — muốn không phạt thì **giữ bậc, sửa tiền về 0**, đừng xoá bậc)
- [ ] Ô **“Đoàn phí công đoàn (NV đóng)”** đã khai chưa? (Để 0 thì đoàn viên cũng ra 0 đồng)
- [ ] Ô **“Không đóng BHXH nếu nghỉ không lương từ”** có đang là 14 không? (**Để 0 là TẮT LUẬT**)

### B. Hồ sơ nhân viên

- [ ] Nhân viên mới đã khai ô **“Lương cơ bản (đóng BH)”** chưa? (Chỉ có cục lương gộp cũ ⇒ **bảo hiểm 0 và đoàn phí 0, âm thầm, không cảnh báo**)
- [ ] Ai đổi lương giữa tháng: nhớ **cả tháng ăn mức MỚI**, không chia đôi
- [ ] Ô tích **đoàn viên** / **bảo hiểm đóng nơi khác** / số **người phụ thuộc** đã đúng chưa?
- [ ] Ai còn số trong ô **“Các khoản phụ cấp (số cũ, gộp một cục)”** mà đã tách thành khoản riêng ở bảng “Khoản thu nhập”? ⇒ **Đang trả GẤP ĐÔI mỗi tháng.** Bấm “Đưa về 0 sau khi đã tách” rồi **bấm “Lưu điều chỉnh”**, mở lại kiểm ô đó đã biến mất chưa (mục 4.3)
- [ ] **Chế độ thuế và ô tích giảm trừ bản thân: HIỆN KHÔNG SỬA ĐƯỢC** (ô đã bị ẩn). Lập danh sách riêng: ai là **thời vụ / hợp đồng dưới 3 tháng / thực tập** và ai **làm hai nơi** ⇒ **tính tay số thuế đúng, ghi sổ ngoài**, đồng thời **báo bộ phận phần mềm mở lại hai ô đó**
- [ ] Số người phụ thuộc có chứng từ đăng ký không? (**Hệ thống không kiểm — kế toán tự chịu trách nhiệm**)

### C. Phiếu

- [ ] Phiếu **tăng ca** đã duyệt đủ chưa? (Không phiếu ⇒ **0 đồng tăng ca** dù có bấm máy)
- [ ] Phiếu **đi muộn / về sớm** đã duyệt hết chưa? (Ảnh hưởng cả phạt trễ lẫn chuyên cần)
- [ ] Phiếu **tạm ứng / lương đợt 1** khai đúng tháng chưa? (**Khai nhầm kỳ = tiền đã đưa mà lương không trừ, không có cảnh báo**)
- [ ] Ai được trả **lương đợt 1** tháng này: đã **lập phiếu** (nút “+ Phiếu lương đợt 1”) và đã bấm **“Duyệt”** chưa? (Khai số ở ô “Lương trả 1 lần (đợt 1)” trong hồ sơ **KHÔNG trừ đồng nào** — mục 11.1)
- [ ] Có phiếu ứng nào **mới duyệt hoặc mới hủy** sau lần tính lại gần nhất không? ⇒ **Phải bấm “↻ Tính lại”**, sửa một ô không đọc lại

### D. Sau khi bấm “↻ Tính lại”

- [ ] Dòng nào đang **khoá tay ô “Đi trễ / nghỉ KP”** (nhãn “đã sửa tay”)? ⇒ Phạt trễ **không tự tính lại**
- [ ] Nhân viên **không phải đoàn viên** mà vẫn có tiền đoàn phí? ⇒ Ai đó đã sửa một ô trên dòng đó — **bấm “↻ Tính lại” để xoá về 0**
- [ ] Nhân viên **thử việc** mà có ai đó sửa mức tháng? ⇒ **Lương công có thể đội +25% — kiểm tay**
- [ ] Cột **“Tăng ca”** có tiền mà nhân viên không tăng ca giờ nào? ⇒ Đó là phần cộng thêm ngày lễ/Chủ nhật hoặc tiền ngày “Nghỉ 1×” — **đúng**
- [ ] Dòng nào có tiền ở cột **“Đợt 1 / Tạm ứng”** đúng bằng số trên phiếu đã duyệt chưa? (Duyệt xong mà quên “↻ Tính lại” là **chưa trừ**)
- [ ] Tổng các ô phạt **khác** với chênh lệch trước–sau phạt? ⇒ Phạt **đã chạm trần 30%**, phần vượt **mất luôn**, **ghi ra ngoài** nếu muốn thu tháng sau
- [ ] Dòng nào có **thu nhập chịu thuế lớn hơn tổng thu**? ⇒ **Đúng**, vì thuế tính trên tổng thu **trước** phạt

### E. Trước khi chi tiền

- [ ] Có dòng nào **thực nhận = 0 mà tổng thu > 0**? ⇒ **Sàn 0 đã nuốt tiền**, hệ thống **không ghi nợ** — tính tay phần còn thiếu trước khi giải thích với người lao động
- [ ] Mở vài **phiếu lương** bằng nút **“In”** để đối chiếu: cơm ca, phụ cấp ca theo ca và khoản trừ danh mục **không có cột riêng trên Bảng lương tháng**, chỉ thấy ở phiếu
- [ ] Bấm **“⬇ Xuất Excel”** lưu bản đối chiếu **trước khi** bấm **“🔒 Chốt”**
- [ ] Chốt xong mới hiện nút **“⬇ File chuyển khoản”**. **Sau khi chốt TUYỆT ĐỐI không sửa tab Bảo hiểm & Thuế** — phiếu lương kỳ cũ sẽ đổi số ba dòng bảo hiểm

### F. Hai file Excel xuất ra — đọc trước khi đối chiếu

Vào **Lương → Bảng lương tháng**, chọn tháng. Trên thanh công cụ có **2 nút tải file** (cần quyền *Xuất* của phân hệ Lương). **Hai file khác nhau hoàn toàn, đừng nhầm.**

**1. Nút “⬇ Xuất Excel”** — hiện ngay khi tháng đó đã có bảng lương (kể cả đang nháp).
File tải về tên `bang-luong-2026-05.xlsx`, **một sheet duy nhất** tên “Luong 05-2026”, **21 cột theo đúng thứ tự trái → phải**:

Mã · Họ tên · Phòng/Tổ · Loại · Công · Lương công · Chuyên cần · Phụ cấp · Khoán · Tăng ca · Ca đêm · Ca đêm (giờ×hệ số) · Cơm ca · Phụ cấp ca · Vi phạm · Thưởng · Tổng · BHXH · TNCN · Tạm ứng · Thực lĩnh

Cột **Loại** in ra chữ “Chính thức” hoặc “Thử việc”. File **không có** cột Công đoàn, Lương đợt 1, Ngày công chuẩn, Số tài khoản, Ghi chú, và **không có** cột Điều chỉnh lương.

**2. Nút “⬇ File chuyển khoản”** — **chỉ hiện sau khi đã bấm “🔒 Chốt”** (hoặc đã bấm Đã chi).
File tên `chuyen-khoan-2026-05.xlsx`, một sheet tên “Chuyen khoan”, **đúng 6 cột**:

Mã · Họ tên · Số tài khoản · Ngân hàng · Số tiền · Nội dung

Cột *Số tiền* chính là *Thực lĩnh* của bảng lương; cột *Nội dung* máy ghép sẵn dạng `Luong T05/2026 - <mã NV>`.

> **Ai không có trong file chuyển khoản:** người có **Thực lĩnh ≤ 0** (tạm ứng hoặc lương đợt 1 đã lấy vượt lương tháng) bị bỏ ra. Vì vậy file chuyển khoản **ít dòng hơn** bảng lương là **đúng, không phải mất người**.
> **Vẫn phải soát tay:** ai chưa khai số tài khoản trong hồ sơ nhân sự thì **vẫn có dòng**, chỉ để trống ô **Số tài khoản** và **Ngân hàng** — lọc hết ô trống trước khi đẩy lên ngân hàng.

**Bốn bẫy khi đối chiếu bằng file bảng lương**

- **Đừng cộng ngang để kiểm Thực lĩnh.** `Tổng − BHXH − TNCN − Tạm ứng` **không** ra Thực lĩnh với mọi người, vì máy còn trừ thêm 3 khoản **không có cột trong file**: kinh phí công đoàn, lương đợt 1 đã trả giữa tháng, và khấu trừ theo khoản danh mục (mua đồng phục…). Ai lệch thì mở màn hình, bấm vào dòng nhân viên để xem chi tiết.
- **Cột “Vi phạm” đã bị trừ sẵn trong cột “Tổng”** (đã áp trần 30%) — **không trừ thêm lần nữa**.
- **Cột “Thưởng” không gồm khoản gán cố định theo hồ sơ nhân viên** (những khoản đó nằm trong cột “Phụ cấp”). Cột Thưởng chỉ gồm thưởng phát sinh của tháng và 6 khoản thưởng cũ (thưởng khác, 5S, doanh số, thành tích, phép năm, trả đồng phục). **Cộng cả hai cột là đếm đôi tiền.**
- **File không có cột “Điều chỉnh lương”.** Dòng nào có số ở khoản đó thì cộng ngang các cột **sẽ không khớp cột “Tổng”** — mở phiếu lương của người đó xem có dòng “Điều chỉnh lương” không (mục 4.5).

**Lưu ý cuối:** file xuất ra **luôn gồm toàn bộ nhân viên của kỳ**, **không** chạy theo ô tìm kiếm / bộ lọc Phòng-Tổ / nút Chính thức-Thử việc đang chọn trên màn hình. Thứ tự dòng là thứ tự bảng lương tạo ra — không xếp theo tên, không nhóm theo phòng; muốn xem theo phòng thì tự sắp xếp trong Excel.

---

---

# 16. BẢNG TRA THAM SỐ — KHAI Ở ĐÂU

## 16.1. Khai ở **Lương → Cấu hình lương → Cơ chế lương theo bộ phận**

| Ô trên màn | Mặc định | Nhân vào đâu | Cảnh báo |
|---|---|---|---|
| % lương thử việc | **80%** (= hệ số 0,80) | Nhân vào lương theo công **và** đơn giá giờ tăng ca | ⚠️ Luật (Điều 26 Bộ luật Lao động) tối thiểu **85%** — số đang khai **thấp hơn luật**, sửa ngay ở màn này. Không nhân vào chuyên cần, phụ cấp, cơm ca, thưởng |
| Công tối thiểu để hưởng cơm / phụ cấp ca | 0,5 | Ngưỡng công của một ngày để được suất | ⚠️ Khai 0 ⇒ **ngày treo cũng có suất** |
| Tăng ca — ngày thường | 1,5 | Giờ tăng ca ngày thường | Chỉ nhận từ 1 đến 5 |
| Tăng ca — ngày nghỉ tuần | 2,0 | Giờ tăng ca ngày nghỉ tuần | Chỉ nhận từ 1 đến 5 |
| Tăng ca — ngày lễ | 3,0 | Giờ tăng ca ngày lễ | Chỉ nhận từ 1 đến 5 |
| Làm nguyên công — ngày nghỉ tuần | 2,0 | Đi làm nguyên công ngày nghỉ tuần | **Chỉ trả phần chênh** (2 − 1) |
| Làm nguyên công — ngày lễ | 3,0 | Đi làm nguyên công ngày lễ | **Chỉ trả phần chênh** (3 − 1) |
| Phụ cấp làm ban đêm | 30% | Phần đêm của giờ **tăng ca** ban đêm | Khác hệ số ca đêm của từng ca |
| Phụ cấp tăng ca đêm | 20% | Nhân với **hệ số Làm nguyên công** của loại ngày | Không phải nhân với hệ số Tăng ca |
| Công tắc **Chuyên cần** (theo tổ) | Chưa khai = BẬT | Tắt ⇒ chuyên cần 0 đ | |
| Công tắc **Tăng ca** (theo tổ) | Chưa khai = BẬT | Tắt ⇒ mất cả phần cộng thêm lễ/Chủ nhật và tiền ngày “Nghỉ 1×” | |
| Công tắc **Lương khoán / sản lượng** (theo tổ) | Chưa khai thì lấy theo công tắc **“Làm khoán”** của phòng ban | Bật ⇒ **ép tắt Tăng ca cả tổ** | ⚠️ Cột Khoán hiện luôn = 0, nên bật công tắc này = **cả tổ mất tăng ca mà không được bù gì**. **Hãy để TẮT**, tính tiền khoán tay rồi nhập vào “Khoản phát sinh tháng này” |

## 16.2. Khai ở **Lương → Cấu hình lương → Bảo hiểm & Thuế**

> ⚠️ **Khai được mức 10%, nhưng chưa gán được cho ai.** Từ 08/08/2026, hai ô *Thuế suất khấu trừ
> tại nguồn* và *Ngưỡng bắt đầu khấu trừ* đã có mặt ngay trong khối **Thuế thu nhập cá nhân** ở màn
> này — luật đổi mức thì kế toán tự sửa, không phải nhờ ai.
>
> Nhưng ô chọn **Cách tính thuế TNCN** của từng người thì **vẫn đang bị ẩn**. Nên hiện **chưa đưa
> được ai sang diện khấu trừ 10%** — lao động hợp đồng dưới 3 tháng vẫn đang bị tính như nhân viên
> dài hạn. **Tính tay và ghi sổ ngoài** cho tới khi bộ phận phần mềm mở lại ô đó.

| Ô trên màn | Mặc định | Cảnh báo |
|---|---|---|
| Cột “NLĐ (%)” của BHXH / BHYT / BHTN | 8 / 1,5 / 1 | Đây là số **trừ thật** |
| Cột “NSDLĐ (%)” của BHXH / BHYT / BHTN | 17,5 / 3 / 1 | ⚠️ **Không ra tiền** — chỉ để tham chiếu |
| TNLĐ-BNN (công ty đóng) | 0,5% | ⚠️ **Không ra tiền** — chỉ hiển thị cho nhóm bảo hiểm đóng nơi khác |
| Trần đóng BHXH + BHYT | 50.600.000 | ⚠️ **Khai 0 = TẮT TRẦN**, đóng trên toàn bộ lương |
| Trần đóng BHTN | 106.200.000 | ⚠️ **Khai 0 = TẮT TRẦN**. Hai trần áp riêng |
| Đoàn phí công đoàn (NV đóng) | **0** | Chủ phải tự khai (mẫu 0,5%) |
| Trần khấu trừ kỷ luật | 30% | ⚠️ **Khai 0 = TẮT TRẦN**, không phải cấm trừ |
| Không đóng BHXH nếu nghỉ không lương từ | 14 ngày | ⚠️ **Khai 0 = TẮT LUẬT**, không phải miễn cả xưởng |
| Giảm trừ bản thân | 15.500.000 | |
| Giảm trừ mỗi người phụ thuộc | 6.200.000 | |
| Bảng biểu thuế (Bậc / Thu nhập tính thuế đến / Thuế suất) | 5 bậc | ⚠️ Xoá bớt thì không mọc lại; xoá sạch thì **tự tái sinh**. Màn này **không kiểm tra gì** |
| **Thuế suất khấu trừ tại nguồn** cho lao động thời vụ / hợp đồng dưới 3 tháng / thực tập | **10%** | Nằm trong khối *Thuế thu nhập cá nhân*, ngay dưới ô *Giảm trừ mỗi người phụ thuộc*. ⚠️ **Khai 0% ⇒ cả nhóm này ra thuế 0 đ** (màn có nhắc, nhưng vẫn cho lưu). Nhóm này **không có giảm trừ gia cảnh, không được trừ bảo hiểm** khi tính thuế — với họ “thu nhập tính thuế” bằng đúng “thu nhập chịu thuế” |
| **Ngưỡng bắt đầu khấu trừ tại nguồn** | **2.000.000** | Cùng chỗ với dòng trên. Ngưỡng so trên **TỔNG thu nhập chịu thuế cả tháng**, không phải mỗi lần trả. Từ 2.000.000 trở lên là khấu trừ **10% trên TOÀN BỘ**, không phải phần vượt. ⚠️ **Khai 0 ⇒ khấu trừ từ đồng đầu tiên** |
| Bảng khấu trừ đi trễ / về sớm (Bậc / Đến phút / Số tiền một lần) | 4 bậc: **≤15 phút 20.000 đ · ≤30 phút 40.000 đ · ≤60 phút 100.000 đ · trên 60 phút 150.000 đ** | ⚠️ Trên hệ thống cũ bảng **có thể đang trống ⇒ phạt đi trễ ra 0 đ cho cả xưởng**. Chỉ cần mở màn này (hoặc bấm “↻ Tính lại” một lần) là 4 bậc tự nạp, rồi sửa lại theo nội quy công ty. Phạt tính **một lần / ngày vi phạm**, không nhân theo số phút |

## 16.3. Khai ở nơi KHÁC

| Tham số | Khai ở màn nào | Mặc định | Ghi chú |
|---|---|---|---|
| Phụ cấp cơm (đ) của ca | Chấm công → Khai ca → Ca làm việc | 25.000 | Theo từng ca |
| Phụ cấp ca (đ) của ca | Chấm công → Khai ca → Ca làm việc | 50.000 | Theo từng ca |
| Hệ số ca đêm của ca | Chấm công → Khai ca → Ca làm việc | 1,3 | **Chỉ áp cho ca có tick “Ca qua đêm”** |
| Dung sai đi muộn (phút) | Chấm công → Khai ca → Ca làm việc | 5 | **Không** áp cho về sớm |
| Tuần làm việc chuẩn | Chấm công → Lịch & Ngày lễ | — | Quyết định công chuẩn |
| Ngày lễ / Làm bù / Nghỉ 1× | Chấm công → Lịch & Ngày lễ | — | Quyết định hệ số ngày |
| Lương cơ bản (đóng BH) | Lương → Lương nhân viên → Thiết lập lương | — | Gốc lương **và** gốc đóng bảo hiểm |
| Lương trách nhiệm | như trên | — | Vào mức nền; **không** vào gốc bảo hiểm, **không** vào ngày phép |
| Thưởng chuyên cần | như trên | 0 | **Nơi duy nhất** khai tiền chuyên cần |
| Phụ cấp thâm niên | như trên | 0 | Nằm trong cột Phụ cấp |
| Số tiền khoản danh mục của từng người | như trên, bảng “Khoản thu nhập theo danh mục” | — | **Nơi duy nhất** khai tiền khoản danh mục |
| Ô tích “Đoàn viên công đoàn” | như trên | **Tắt** | Phải bật cho từng người |
| Ô tích “Bảo hiểm đóng ở nơi khác” | như trên | Tắt | ⇒ Bảo hiểm 0, **đoàn phí vẫn trừ** |
| Lương trả 1 lần (đợt 1) | như trên | 0 | **Chỉ là số ĐIỀN SẴN, khai ở đây KHÔNG trừ đồng nào.** Muốn thật sự trả đợt 1: **Lương → tab Tạm ứng → “+ Phiếu lương đợt 1” → duyệt** — duyệt xong mới trừ vào lương |
| Tên / loại (Thu, Trừ) / ô tích **Chịu thuế** của khoản | Lương → Cấu hình lương → Danh mục khoản thu nhập | — | Danh mục **không có mức tiền** |
| Khoản phát sinh riêng của kỳ | Lương → Bảng lương tháng → Sửa lương → “Khoản phát sinh tháng này” | — | Đường khai thưởng mới |
| Phiếu tạm ứng / lương đợt 1 | Lương → tab Tạm ứng | — | Chỉ phiếu **Đã duyệt** mới trừ |
| Đơn giá khoán theo tổ | Lương → tab Lương khoán | — | Chưa gắn tổ thì không bao giờ khớp |
| **Công tắc “Làm khoán”** của phòng ban | Phòng ban **hoặc** Cấu hình lương | Tắt | ⚠️ Bật = **cắt tăng ca cả tổ**, mà cột Khoán vẫn 0 — hãy để TẮT |
| Cách tính thuế TNCN · ô tích “Áp dụng giảm trừ bản thân” | **Lương → Lương nhân viên → Sửa lương**, khối “Thuế TNCN” (hồ sơ nhân sự chỉ hiện để xem) | Luỹ tiến · Bật | **Kế toán tự đổi được**, không cần nhờ ai — miễn là tài khoản có quyền xem/sửa dữ liệu lương của hồ sơ nhân sự. Đổi cách tính thuế có **hộp xác nhận** vì bỏ luỹ tiến = mất toàn bộ giảm trừ gia cảnh. Thiếu quyền thì ô chuyển chỉ-đọc kèm câu “Tài khoản của bạn không có quyền sửa nhóm dữ liệu lương/BHXH” — **xin cấp quyền**, không phải lỗi hệ thống |
| Số người phụ thuộc | **Nhân sự → Hồ sơ nhân viên → tab Lương & BHXH → Sửa** (và ở bước Lương & BHXH khi thêm nhân viên) | 0 | Ô số nhập tay, sửa trực tiếp. ⚠️ Hệ thống **không kiểm chứng từ đăng ký người phụ thuộc** — gõ bao nhiêu giảm trừ bấy nhiêu |

---

# PHỤ LỤC A — NHỮNG CỘT DỄ NHẦM NHẤT TRÊN PHIẾU LƯƠNG

| Nhìn thấy | Đừng nhầm với | Sự thật |
|---|---|---|
| **“Các khoản phụ cấp (số cũ, gộp một cục)”** | Một ô chết vì đang mờ, chỉ đọc | Ô **KHÔNG gõ được nhưng tiền vẫn được trả đủ** mỗi tháng, nằm trong cột Phụ cấp. Sau khi đã tách thành từng khoản riêng bên trên, **BẮT BUỘC bấm “Đưa về 0 sau khi đã tách” rồi Lưu** — quên là **trả hai lần**, tháng nào cũng lặp |
| **“Trong đó: lương ngày phép”** | Dòng **“Phép năm”** (kỳ cũ) | Dòng đầu **tự tính và ĐÃ nằm trong “Lương theo công”** — **không cộng lại**. Dòng sau là số gõ tay của kỳ cũ, cộng thẳng vào tổng thu. Nhầm = **cộng đôi tiền phép** |
| **“Tăng ca”** | Tiền tăng ca thuần | Cột này còn chứa **phần cộng thêm ngày lễ / Chủ nhật** và **tiền ngày “Nghỉ 1×”**. Không tăng ca giờ nào vẫn có thể thấy tiền |
| **“Phụ cấp ca đêm (giờ × hệ số)”** | **“Phụ cấp ca (khai tay — đã ngưng)”** | Dòng đầu **tự tính theo giờ, đang dùng**. Dòng sau là số phẳng gõ tay, **luôn = 0 với kỳ mới** |
| **Cột “BHXH”** trên Bảng lương tháng | Riêng BHXH 8% | Là **TỔNG CẢ BA**: BHXH 8% + BHYT 1,5% + BHTN 1%. **Chỉ bằng 10,5% khi mức đóng dưới cả hai trần** — hai trần khác nhau nên lương cao ra tỷ lệ thấp hơn. Đúng phải là: (mức đóng, chặn ở 50.600.000) × 9,5% **+** (mức đóng, chặn ở 106.200.000) × 1%. *Ví dụ mức đóng 60.000.000:* 50.600.000 × 9,5% = 4.807.000, cộng 60.000.000 × 1% = 600.000, tổng **5.407.000 đ** (≈ 9%), **không phải 6.300.000 đ** — nhẩm 10,5% là thừa 893.000 đ/người/tháng |
| **“Thu nhập chịu thuế”** | **“Thu nhập tính thuế”** | Cột đầu là số **TRƯỚC** giảm trừ (chủ hỏi “tổng lương chịu thuế” là số này). Cột sau là **SAU** khi trừ bảo hiểm và giảm trừ — **chỉ số này mới tra biểu thuế**. “Thu nhập tính thuế” **xem được ngay ở dòng nhắc đầu cửa sổ Sửa lương**; còn “Thu nhập chịu thuế” **không hiện ở đâu**, phải tính tay theo mục 9.1 |
| **“Phụ cấp thâm niên”** | Một khoản riêng ngoài Phụ cấp | Là số **nằm trong** cột Phụ cấp — **đừng cộng lại** |
| **“Trả đồng phục”** | **“Đồng phục / phạt 5S”** | Dòng đầu là khoản **THU** (cộng lương). Dòng sau là khoản **PHẠT** |
| **“Điện thoại vượt trội”** | Một khoản thu hồi bình thường | Bị xếp **chung rổ phạt kỷ luật** và **ăn vào trần 30%** |
| **“Điều chỉnh lương”** (cột THU) | **“Giảm trừ khác”** (cột TRỪ) | **HAI khoản KHÁC NHAU, đừng gộp.** “Điều chỉnh lương” cộng ± thẳng vào tổng thu, **không bị trần 30%**, số âm còn **giảm thu nhập chịu thuế và nới trần phạt** — hiện **không có ô nhập trên bất kỳ màn nào**, muốn dùng phải nhờ kỹ thuật. “Giảm trừ khác” là **khoản PHẠT KỶ LUẬT**: ô “Giảm trừ khác (trừ)” trên cửa sổ Sửa lương ghi vào đây, **chỉ nhận số dương**, **BỊ KẸP TRẦN 30%** (Điều 102 Bộ luật Lao động) và **KHÔNG giảm thuế TNCN**. Muốn cộng/trừ một khoản mới thì dùng **“Khoản phát sinh tháng này”** |
| **“THỰC NHẬN”** in cuối phiếu | Tổng lương cả tháng | Là số **CÒN PHẢI TRẢ (đợt 2)** — đã trừ “Thanh toán lương đợt 1” và “Tạm ứng đã nhận”, dù trên phiếu không in chữ “đợt 2” nào. Trên Bảng lương tháng hai khoản này gộp chung một cột **“Đợt 1 / Tạm ứng”**, trên phiếu thì tách hai dòng — **cùng một số tiền, đừng đếm hai lần** |
| **“TỔNG TRỪ”** | (Tổng thu − Thực nhận) | **Không khớp nhau khi phạt bị kẹp trần**, vì cột TRỪ in **số phạt THÔ** |

---

# PHỤ LỤC B — Ô KHAI BAO NHIÊU CŨNG KHÔNG RA TIỀN

Đừng khai, đừng tin, đừng hứa với người lao động dựa vào những ô này.

| Ô / tham số | Nhìn thấy ở | Thực tế |
|---|---|---|
| **Mức đóng bảo hiểm khai riêng** | Hồ sơ lương | **Không được đọc** — mức đóng luôn bằng ô “Lương cơ bản (đóng BH)” |
| **Phụ cấp ca (đã ngưng)** | Thiết lập lương | Chỉ đọc, **luôn tính bằng 0**. Từ 21/08/2026 ô này **chỉ còn hiện với người còn số cũ** — ai để 0 thì không thấy ô này nữa |
| Cột **“NSDLĐ (%)”** của BHXH / BHYT / BHTN | Bảo hiểm & Thuế | Chỉ tham chiếu, **không nhân ra tiền** |
| **TNLĐ-BNN (công ty đóng)** | Bảo hiểm & Thuế | Chỉ hiển thị cho nhóm bảo hiểm đóng nơi khác, **không ghi vào bảng lương** |
| Ô tích **“cộng vào gốc đóng BH”** của khoản danh mục | Danh mục khoản thu nhập | Bật lên **không có tác dụng gì** |
| **Công đoạn ghi trên bảng đơn giá khoán** | Tab Lương khoán | **Không còn dùng** — hệ thống nay ghép đầu việc khoán theo **định mức khai ở từng công đoạn**, không đọc ô Công đoạn trên bảng đơn giá nữa. Công đoạn chưa khai định mức thì **không chọn được đầu việc nào**, dù bảng đơn giá của tổ đã khai đầy |
| **Bậc thưởng / phạt tổ trưởng theo tỷ lệ hàng lỗi** | Cấu hình lương | **Chưa nối** — khai không ra tiền. Băng cảnh báo trên màn đang nói đúng |
| **6 khoản thưởng cũ** (Phép năm, Thưởng 5S, Thưởng doanh số, Thưởng thành tích, Trả đồng phục, Thưởng khác) | Phiếu lương, khối “Khoản kỳ cũ” | **Chặn khai mới** — khai qua “Khoản phát sinh tháng này” |
| **Ô “Công chuẩn / tháng”** | Màn Lương | Hiện chữ “Tự tính theo Lịch & Ngày lễ”, **không gõ tay được** |
| **Trần tạm ứng** | — | Đã gỡ, không còn giới hạn số tiền ứng |
| **Mức chuyên cần mặc định toàn công ty** | — | Không tồn tại — chỉ khai ở từng hồ sơ nhân viên |

> ⚠️ **Ô “Các khoản phụ cấp (số cũ, gộp một cục)” KHÔNG nằm trong danh sách này.** Ô đó mờ và chỉ đọc nhưng **tiền vẫn được trả đủ** — xem Phụ lục A.

---

# PHỤ LỤC C — VIỆC HỆ THỐNG CHƯA LÀM, PHẢI TÍNH TAY

Ghi thẳng để không ai chờ máy làm hộ.

| # | Việc | Trạng thái | Làm thế nào hiện nay |
|---|---|---|---|
| 1 | **Lương khoán theo sản lượng thực tế** | **Hệ thống chưa làm phần này** — **không có chỗ nào nhập sản lượng thực tế**, nên cột Khoán trên bảng lương **luôn = 0 với mọi người**. Đừng đi tìm màn nhập sản lượng | Tính tay → nhập vào “Khoản phát sinh tháng này” (khoản **chịu thuế**). Đồng thời **TẮT công tắc “Lương khoán / sản lượng”** để tổ không mất tăng ca |
| 2 | **Thưởng / phạt tổ trưởng theo tỷ lệ hàng lỗi** | **Chưa nối** — khai bậc không ra tiền | Tính tay → nhập qua khoản phát sinh |
| 3 | **Quyết toán thuế thu nhập cá nhân cả năm** | **Hệ thống chưa làm phần này** — chỉ có biểu tháng, không cộng dồn 12 tháng, không xử lý người vào / nghỉ giữa năm | Bảng tính Excel xuất ra từ Bảng lương tháng **chỉ cộng được Tổng thu, BHXH, TNCN, Thực lĩnh** — **KHÔNG có cột “Thu nhập chịu thuế” / “Thu nhập miễn thuế” / Đoàn phí / Lương đợt 1 / Khoản trừ danh mục**. Muốn quyết toán phải **tự dựng lại số chịu thuế từng tháng theo mục 9.1**, hoặc nhờ kỹ thuật xuất thêm cột |
| 4 | **“Thu nhập TÍNH thuế” và “Thu nhập miễn thuế” trên phiếu lương** | Khối hai ô này **đang bị tắt hiển thị**, phiếu in ra không có. Riêng **“Thu nhập CHỊU thuế” thì chưa từng được in ở đâu trên màn**, dù hệ thống đã lưu sẵn số này trên từng dòng lương | “Thu nhập tính thuế” **không phải tính tay** — xem ngay ở dòng nhắc đầu cửa sổ Sửa lương. Muốn số **“chịu thuế”** để đối chiếu quyết toán: **tính tay theo mục 9.1**, hoặc nhờ kỹ thuật lấy ra từ số đã lưu |
| 5 | **Báo cáo tổng chi phí bảo hiểm phía công ty** | **Hệ thống chưa làm phần này** — bảng lương không lưu phần công ty đóng | Cộng tay theo **hai trần riêng**: (a) **min(mức đóng; 50.600.000) × 21%** — gồm BHXH 17,5% + BHYT 3% + TNLĐ-BNN 0,5%; (b) cộng thêm **min(mức đóng; 106.200.000) × 1%** — BHTN. Chỉ khi mức đóng **dưới 50.600.000** mới được nhân gọn một lần **22%** |
| 6 | **Sổ theo dõi phần phạt vượt trần 30%** | **Không có sổ nợ phạt** — phần vượt bỏ luôn, không dồn kỳ sau | Ghi ra ngoài; muốn thu tiếp thì tự gõ lại vào ô phạt kỳ sau, **cẩn thận thu trùng** vì ô phạt giữ nguyên số thô khi tính lại |
| 7 | **Theo dõi phần tiền bị hai lần chặn sàn 0 nuốt mất** | **Không ghi nợ, không chuyển kỳ sau** | Kiểm tay các dòng có thực nhận 0 đ mà tổng thu > 0 |
| 8 | **Kiểm tra chứng từ đăng ký người phụ thuộc** | Hệ thống **không kiểm** — gõ bao nhiêu giảm trừ bấy nhiêu | Kế toán tự giữ hồ sơ và tự đối chiếu |
| 9 | **Kiểm tra điều kiện hợp lệ của cam kết 08** | Hệ thống **không kiểm, không cảnh báo, không có hạn theo năm** | Rà tay đầu mỗi năm |

> **Không còn nằm trong danh sách này:** đổi cách tính thuế TNCN, tắt giảm trừ bản thân, sửa số người phụ thuộc. **Cả ba kế toán tự bấm được** (xem bảng 16.3) — chỉ cần đủ quyền, không phải nhờ kỹ thuật.

---

## LỜI DẶN CUỐI

Bốn câu phải thuộc:

1. **Mẫu số luôn là công chuẩn của tháng.** Ai chia cho công thực là sai từ dòng đầu.
2. **Mức đóng bảo hiểm bám ô “Lương cơ bản (đóng BH)”**, không bám mức nền, không chia theo công.
3. **Cột “Tăng ca” không chỉ là tăng ca** — trong đó còn phần cộng thêm ngày lễ, Chủ nhật và tiền ngày “Nghỉ 1×”.
4. **Sửa một ô xong thì bấm “↻ Tính lại” rồi mới đọc số.** Đây là câu cứu được nhiều tiền nhất trong cả cuốn sổ này.
