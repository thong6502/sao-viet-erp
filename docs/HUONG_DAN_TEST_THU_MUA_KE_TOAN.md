# Hướng dẫn kiểm thử — Thu mua → Đợt giao → Phiếu chi → Công nợ

Bản **06/08/2026**. Tài liệu để **người dùng tự bấm theo và đối chiếu kết quả**, không cần biết kỹ
thuật. Làm tuần tự từ đầu tới cuối là chạy hết một vòng đời của đơn hàng.

Mỗi bước có ô **Kết quả mong đợi**. Đúng thì tích ✅, sai thì ghi số hiệu bước (VD `7.3`) và chụp
màn hình.

> ### Bản này khác bản trước ở bốn chỗ — đọc trước khi test
>
> | Trước | Bây giờ |
> |---|---|
> | Nhận hàng = một cú bấm cho cả đơn | **Ghi từng ĐỢT GIAO**; hàng về tới đâu nợ tới đó |
> | Phiếu chi có trạng thái *Chờ chi* rồi mới *Đã chi* | **Lập phiếu chi = tiền đã ra**. Không còn *Chờ chi* |
> | Sửa được phiếu chi đã lập | **KHÔNG sửa nữa** — chỉ đính kèm tài liệu. Sai thì huỷ rồi lập lại |
> | Hạn trả nằm trên phiếu chi | **Hạn trả nằm ở đợt giao** = ngày giao + số ngày NCC cho nợ |
>
> Nếu bạn từng test bản trước, ba chỗ hay bị tưởng là lỗi: không tìm thấy nút *Xác nhận đã chi*
> (đã bỏ), không thấy cột *Chờ chi* (đã bỏ), và phiếu vừa lập đã mang trạng thái *Đã chi* (đúng).

---

## 0. Chuẩn bị

### 0.1 Dữ liệu hiện tại

Dữ liệu giao dịch đã được **xoá sạch** ngày 06/08/2026: không còn yêu cầu mua hàng, phiếu mua, phiếu
chi, phiếu thu nào. Số chứng từ chạy lại từ **PC00001**.

**Còn giữ:** 2 nhà cung cấp + 3 mặt hàng của họ. Không còn tài khoản ngân hàng nào (0 của công ty,
0 của NCC) — cần cho phần test UNC ở mục 9.

### 0.2 Khởi động lại backend TRƯỚC KHI TEST

Bản này thêm bảng và cột mới. **Bắt buộc restart uvicorn** — ở môi trường này hot-reload không đáng
tin, không restart thì màn chạy bản cũ và bạn sẽ báo nhầm là lỗi.

Sau khi restart, kiểm nhanh chỉ có **một** bản đang chạy:

```bash
netstat -ano | findstr :8000
```

Ra **đúng một dòng**. Ra nhiều dòng nghĩa là có nhiều bản chồng nhau — cùng một thao tác sẽ cho kết
quả khác nhau tuỳ lần. Báo lại để dọn trước khi test tiếp.

### 0.3 Cần bao nhiêu tài khoản

Luồng này **cố ý bắt buộc nhiều người** — một người không làm được từ đầu tới cuối:

| Vai | Làm gì | Vì sao phải tách |
|---|---|---|
| **Nhân viên bộ phận** (Kho, Sản xuất…) | Tạo yêu cầu mua hàng | Người cần hàng mới biết cần gì |
| **Nhân viên mua hàng** | Lập phiếu mua, ghi đợt giao | |
| **Trưởng bộ phận / Giám đốc** | Duyệt đơn · Đóng đơn · Mở lại đơn | Ai đề xuất chi tiền thì không được tự đồng ý chi |
| **Kế toán** | Lập phiếu chi, xem công nợ | Người quyết chi ≠ người xuất tiền |

> ⚠️ **Người lập phiếu KHÔNG duyệt được phiếu của chính mình** — kể cả giám đốc. Thấy báo lỗi ở
> bước đó là **đúng**.

### 0.4 Cần khai trước

- 2 nhà cung cấp, mỗi NCC khai **danh mục mặt hàng** (tên hàng, đơn vị, đơn giá). Không khai thì
  lập phiếu mua bị chặn — chốt này ngăn chọn nhầm NCC không bán món đó.
- Hai NCC nên bán **hai mặt hàng khác nhau** (VD: NCC A bán *Giấy Duplex*, NCC B bán *Băng keo*) —
  cần cho phần tách phiếu ở mục 3.

---

## 1. ⭐ MỚI — Hạn mức và số ngày cho nợ của nhà cung cấp

**Vào:** `Thu mua → Nhà cung cấp` → mở một NCC → **Sửa**

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 1.1 | Tìm hai ô mới: **Hạn mức công nợ (VNĐ)** và **Số ngày cho nợ** | Cả hai ô có mặt |
| 1.2 | NCC A: hạn mức **3.000.000**, số ngày cho nợ **30** | Lưu được |
| 1.3 | NCC B: **để trống cả hai** | Lưu được — không bắt buộc |
| 1.4 | Nhập hạn mức **âm** | ❌ Bị chặn |

> **Hai ô này khác nhau, đừng lẫn:**
> - **Hạn mức** = trần **số tiền** được nợ NCC đó. `0`/để trống = **không đặt hạn mức**, không bao
>   giờ báo vượt.
> - **Số ngày cho nợ** = NCC cho nợ bao nhiêu **ngày** kể từ ngày giao. Dùng để tính hạn trả.
>   **`0` nghĩa là "trả ngay"** (giao hôm nay, mai chưa trả là đỏ). **Để trống nghĩa là "chưa đặt
>   hạn"** — đợt giao của NCC đó sẽ **không bao giờ vào cột Quá hạn**, nhưng được đẩy lên đầu danh
>   sách kèm badge để bạn đi khai. Hai thứ này rất khác nhau.

✅ **Chốt mục 1:** NCC A có hạn mức + số ngày; NCC B không có (để so ở mục 10).

---

## 2. Bộ phận gửi yêu cầu mua hàng

**Vào:** `Thu mua → Yêu cầu mua hàng` · Đăng nhập bằng **nhân viên bộ phận**

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 2.1 | Bấm **Tạo yêu cầu**, chọn nhóm nguồn, chọn ngày cần hàng | Form mở ra |
| 2.2 | ⭐ **MỚI** — nhìn phần đầu form | Chỉ còn **MỘT** ô *Nội dung / mục đích*. Ô *Ghi chú* riêng đã bỏ |
| 2.3 | ⭐ Gõ nội dung **dài ~1 trang** (600–1000 chữ) rồi lưu | Lưu được, mở lại thấy **nguyên văn** — không cụt giữa chừng |
| 2.4 | Thử chọn **ngày cần hàng ở quá khứ** | ❌ Bị chặn — không xin hàng cho ngày đã qua |
| 2.5 | Để trống ô *Nội dung / mục đích* rồi lưu | ❌ Bị chặn, báo thiếu *Nội dung / mục đích* |
| 2.6 | Thêm **2 dòng**: một dòng hàng của NCC A, một dòng của NCC B | Cả hai dòng nhận |
| 2.7 | Lưu | Yêu cầu hiện trong danh sách, trạng thái **Chờ mua** |
| 2.8 | ⭐ Mở **yêu cầu CŨ** (lập trước 07/08/2026) | Ô nội dung có đủ chữ của cả *mục đích* lẫn *ghi chú* cũ, nối bằng dấu ` — ` |

✅ **Chốt mục 2:** yêu cầu ở *Chờ mua*, đủ 2 dòng hàng, một ô nội dung duy nhất.

---

## 3. Thu mua lập phiếu — kiểm tra TÁCH PHIẾU

**Vào:** `Thu mua → Mua hàng` · Đăng nhập bằng **nhân viên mua hàng**

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 3.1 | Bấm **Lập phiếu từ yêu cầu**, chọn yêu cầu vừa tạo | Form tự đổ ra 2 dòng hàng |
| 3.2 | Nhìn cột **Nhà cung cấp** của từng dòng | Máy đã tự gán sẵn NCC **rẻ nhất** cho từng dòng |
| 3.3 | Thử sửa **Vật tư / ĐVT / Số lượng** | ❌ Không sửa được — đó là số bộ phận đã xin |
| 3.4 | Thử **thêm dòng** / **xoá dòng** | ❌ Không có nút |
| 3.5 | Đổi NCC của một dòng sang NCC **không bán** món đó | ❌ Bị chặn, báo rõ |
| 3.6 | Xem khối **"Phiếu sẽ tạo"** | Báo sẽ tạo **2 phiếu** — mỗi NCC một phiếu |
| 3.7 | Bấm Lưu | Ra **2 phiếu mua hàng** riêng, cùng trỏ về 1 yêu cầu |

> **Vì sao tách:** một phiếu mua là thoả thuận với **một** nhà cung cấp.

✅ **Chốt mục 3:** 2 phiếu mua, mỗi phiếu 1 dòng, cùng một yêu cầu nguồn.

---

## 4. ⭐ Trạng thái yêu cầu khi hai phiếu chạy LỆCH NHAU

Phần dễ sai nhất, làm kỹ.

**Nguyên tắc:** trạng thái yêu cầu luôn lấy theo **phần chậm nhất**. Thà báo bi quan để bộ phận đi
hỏi, còn hơn báo lạc quan để họ ngồi chờ hàng không bao giờ tới.

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 4.1 | Gửi duyệt **cả hai** phiếu | Yêu cầu → **Chờ duyệt** |
| 4.2 | Duyệt **phiếu A** thôi | Yêu cầu **vẫn Chờ duyệt** ⚠️ |
| 4.3 | Duyệt nốt **phiếu B** | Yêu cầu → **Đang mua** |
| 4.4 | Phiếu A: bấm **Đã mua**, rồi ghi **một đợt giao chưa đủ số** | Phiếu A → **Giao một phần**; yêu cầu **vẫn Đang mua** ⚠️ |
| 4.5 | Phiếu A: ghi nốt đợt cho **đủ số đặt** | Phiếu A → **Đã nhận**; yêu cầu **vẫn Đang mua** (phiếu B chưa xong) ⚠️ |
| 4.6 | Phiếu B: **Đã mua** → ghi đợt đủ số | Yêu cầu → **Xong** |

> **Giao một phần** là trạng thái **MỚI**, và nó **suy ra từ đợt giao** — không ai gõ tay được.
> Bước 4.4 là chỗ hay hiểu nhầm: hàng đã về một phần thì đã có công nợ, nhưng yêu cầu **chưa xong**.

### 4.7 Khi một phiếu bị TỪ CHỐI

Làm lại với một yêu cầu mới (2 phiếu, cùng đến bước đã duyệt):

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 4.7.1 | Phiếu A: đã nhận đủ. **Từ chối phiếu B** | Yêu cầu → **Chờ mua** |
| 4.7.2 | Mở lại phiếu A | Vẫn **Đã nhận** — không bị đụng |
| 4.7.3 | Lập **phiếu mới** cho phần bị từ chối | Lập được (vì yêu cầu đã về *Chờ mua*) |
| 4.7.4 | Đưa phiếu mới đi hết | Yêu cầu → **Xong** |

✅ **Chốt mục 4:** yêu cầu luôn phản ánh phần chậm nhất, và không bao giờ kẹt.

---

## 5. Xem tình trạng TỪNG SẢN PHẨM

**Vào:** `Thu mua → Yêu cầu mua hàng` → bấm vào một yêu cầu

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 5.1 | Nhìn bảng **Vật tư đã yêu cầu** | Có cột **Nhà cung cấp** và **Tình trạng** từng dòng |
| 5.2 | Dòng đã nhận hàng | Hiện *Đã nhận* + mã phiếu + số đã nhận |
| 5.3 | Dòng thuộc phiếu bị từ chối | Hiện *Bị từ chối* + nhắc **"Cần lập phiếu lại cho dòng này"** |
| 5.4 | Dòng chưa ai lập phiếu | Hiện *Chờ thu mua lập phiếu* |
| 5.5 | Kéo xuống | Có mục **Phiếu mua đã lập** + NCC + trạng thái |

✅ **Chốt mục 5:** nhìn chi tiết là biết **món nào** đang kẹt.

---

## 6. ⭐ MỚI — Hợp đồng và cọc dự kiến trên phiếu mua

**Vào:** `Thu mua → Mua hàng` → mở phiếu → khối **Hợp đồng & chứng từ**

> ⚠️ **Cọc dự kiến phải khai KHI PHIẾU CÒN NHÁP / CHỜ DUYỆT.** Duyệt xong là khoá.

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 6.1 | Phiếu còn **nháp** — điền **Số hợp đồng** + **Cọc dự kiến** (VD 500.000) | Lưu được |
| 6.2 | Gửi duyệt → duyệt xong → mở lại khối này | Ô **Cọc dự kiến** hiện *(đã duyệt — khoá)*, **không sửa được** |
| 6.3 | Đơn đã duyệt — sửa **Số hợp đồng** | ✅ **Vẫn sửa được** — hợp đồng thường ký sau khi duyệt |
| 6.4 | Tải lên **ảnh/PDF hợp đồng** (kể cả sau khi duyệt) | Tải được, hiện thumbnail |
| 6.5 | Tải file **không phải ảnh/PDF** (VD `.docx`) | ❌ Bị chặn |
| 6.6 | Tải file **lớn hơn 10 MB** | ❌ Bị chặn |
| 6.7 | Bấm × để xoá một file | Xoá được |
| 6.8 | Sau khi điền cọc dự kiến 500.000, sang **Công nợ phải trả** | Công nợ **KHÔNG** bị trừ 500.000 |
| 6.9 | Sang `Kế toán → Đơn mua hàng`, mở đúng đơn đó | Thấy **Số hợp đồng** và **Cọc dự kiến 500.000** (chỉ đọc) |

> **Bước 6.2 — vì sao khoá:** cọc là một phần của khoản chi mà người duyệt đã đồng ý. Cho sửa sau
> khi duyệt là đổi con số đã ký mà không ai duyệt lại. Cần đổi thì lùi phiếu về nháp rồi duyệt lại.
>
> **Bước 6.8 — vì sao không trừ:** *cọc dự kiến* chỉ để **nhắc**, nó không phải tiền đã chi. Tiền
> cọc THẬT là một **phiếu chi loại Đặt cọc** (mục 9). Nếu cọc dự kiến cũng bị trừ thì khi kế toán
> lập phiếu chi cọc, cọc bị trừ **hai lần** và công nợ ra số âm giả.
>
> **Bước 6.9 — vì sao phải thấy bên Kế toán:** đó là màn kế toán lập phiếu chi. Không thấy thì thu
> mua khai cọc một đằng, kế toán chi một nẻo.

✅ **Chốt mục 6:** cọc khai lúc nháp, khoá sau duyệt, kế toán nhìn thấy, và không đụng vào công nợ.

---

## 7. ⭐⭐ TRỌNG TÂM BẢN NÀY — Ghi ĐỢT GIAO

**Vào:** `Thu mua → Mua hàng` → mở phiếu ở trạng thái **Đã mua** → khối **Các đợt giao**

Chuẩn bị: dùng một phiếu **1.000 tờ × 2.200đ = 2.200.000đ** cho dễ đối chiếu.

### 7.1 Đợt giao đầu tiên

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 7.1.1 | Phiếu chưa bấm **Đã mua** — tìm nút *Ghi đợt giao* | ❌ Chưa có — phải *Đã mua* trước |
| 7.1.2 | Bấm **Đã mua**, rồi bấm **Ghi đợt giao** | Hộp mở ra, ô số của từng mặt hàng **điền sẵn phần còn lại** |
| 7.1.3 | Sửa số nhận thành **400**, để trống ô tiền, bấm **Lưu đợt giao** | Đợt 1 hiện trong bảng, thành tiền **880.000đ** (400 × 2.200) |
| 7.1.4 | Nhìn trạng thái phiếu | Đổi thành **Giao một phần** |
| 7.1.5 | Nhìn dòng tổng dưới bảng đợt | **Đã giao 880.000 · Đã chi 0 · Còn nợ 880.000** |
| 7.1.6 | Sang `Kế toán → Công nợ phải trả` | NCC đó hiện **Còn nợ 880.000đ** |

> **Đây là lỗi lớn nhất mà bản này sửa.** Bản trước: giao 1/3 đợt thì đơn vẫn ở *Đã mua* và màn
> công nợ hiện **0đ** — nhìn vào tưởng không nợ ai, trong khi đã nợ thật.

### 7.2 ⭐ Thành tiền của đợt — MÁY TỰ TÍNH, không ai gõ

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 7.2.1 | Ghi đợt 2: nhận **300**, nhìn ô **Số tiền theo hóa đơn** | Ô để trống, placeholder + dòng gợi ý dưới ô đều là số theo đơn giá (**660.000**) |
| 7.2.1b | Nhìn bảng mặt hàng phía trên | Chỉ có `Vật tư · Đặt · Còn chưa giao · Nhận đợt này` — **không** có cột tiền theo dòng |
| 7.2.2 | Gõ **800.000** vào ô tiền | Dưới ô hiện *"Theo đơn giá là 660.000 — lệch 140.000"*, và **Ghi vào công nợ 800.000** |
| 7.2.3 | Lưu | Bảng đợt hiện **800.000**, kèm dòng nhỏ *"đơn giá: 660.000"* |
| 7.2.4 | Xem công nợ | Cộng đúng **880.000 + 800.000 = 1.680.000** |
| 7.2.5 | Sửa đợt 2, **xoá trắng** ô tiền, lưu | Quay về **660.000** (số theo đơn giá) |

### 7.2b ⭐ Chụp ảnh hóa đơn ngay khi ghi đợt

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 7.2b.1 | Trong hộp **Ghi đợt giao**, kéo xuống mục **Ảnh hóa đơn / phiếu giao hàng** | Có ô chọn tệp |
| 7.2b.2 | Chọn 2 ảnh | Hiện 2 ô kèm chữ **"chờ tải lên"** (viền đứt) |
| 7.2b.3 | Bấm × trên một ô chờ | Bỏ khỏi hàng chờ, chưa đụng gì tới máy chủ |
| 7.2b.4 | Chọn file **không phải ảnh/PDF**, hoặc **>10 MB** | ❌ Báo lỗi ngay tại chỗ, không nhận vào hàng chờ |
| 7.2b.5 | Bấm **Ghi đợt giao** | Đợt lưu xong, ảnh tải lên và gắn vào **đúng đợt vừa ghi** |
| 7.2b.6 | Nhìn cột **Hóa đơn** của đợt đó trong bảng | Có dấu **📎 2** |
| 7.2b.7 | Mở **Sửa** đợt đó | Ảnh đã tải hiện thành thumbnail, bấm × xoá được — hộp **không đóng** |
| 7.2b.8 | Ghi một đợt **không kèm ảnh** | ✅ Vẫn lưu bình thường — hóa đơn về muộn là chuyện thường |

> **Vì sao đặt ảnh ngay trong hộp ghi đợt:** tờ hoá đơn đang cầm trên tay lúc **nhận hàng**. Bắt ghi
> đợt xong rồi quay lại tìm nút đính kèm là kiểu người ta quên.
>
> Ảnh phải **chờ** cho tới khi đợt lưu xong mới tải lên được — đợt chưa tồn tại thì chưa có chỗ để
> gắn file vào. Vì thế bước 7.2b.2 hiện chữ *"chờ tải lên"*: đóng hộp giữa chừng là mất mấy file đó.

> **Vì sao cho gõ tay:** NCC xuất hoá đơn với số tiền không suy được từ đơn giá đặt là chuyện
> thường — gộp cước, bù chênh, làm tròn theo hợp đồng. Công nợ phải bám **chứng từ**, vì chứng từ
> mới là thứ đem đi đối chiếu với NCC. Chỗ lệch vẫn hiện ra để bạn nhìn thấy, chứ không giấu.

### 7.3 ⭐ Trần: tổng các đợt KHÔNG được vượt giá trị đơn

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 7.3.1 | Ghi một đợt với số tiền **5.000.000** (đơn chỉ 2.200.000) | ❌ Bị chặn, báo *"vượt giá trị đơn đã duyệt"* |
| 7.3.2 | Đơn đang có 880.000 + 800.000 = 1.680.000. Ghi đợt mới **600.000** | ❌ Bị chặn — cộng dồn thành 2.280.000 > 2.200.000 |
| 7.3.3 | Ghi đợt mới **520.000** | ✅ Qua — vừa đúng 2.200.000 |

> **Vì sao chặn:** giá trị đơn là con số **giám đốc đã duyệt**. Cho tổng hoá đơn vượt nó là chi quá
> mức đã duyệt mà không qua duyệt lại. Hoá đơn cao hơn đơn thật thì đường đúng là **sửa đơn rồi
> duyệt lại**, không nhét chênh lệch vào đợt giao.

### 7.4 Chặn khai vượt SỐ LƯỢNG đặt

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 7.4.1 | Đơn đặt 1.000, đã giao 700. Ghi đợt mới **400** | ❌ Bị chặn: *"chỉ còn 300 chưa giao"* |
| 7.4.2 | Ghi **300** | ✅ Qua, và phiếu tự chuyển sang **Đã nhận** |

> Số lượng và số tiền là **hai trần riêng**: số lượng chặn theo số đặt, số tiền chặn theo giá trị
> đơn. Một đợt có thể qua trần này mà vướng trần kia.

### 7.5 Sửa / xoá đợt giao

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 7.5.1 | Bấm **Sửa** một đợt **chưa có phiếu chi** | Sửa được ngày, hạn trả, hoá đơn, số lượng, số tiền |
| 7.5.2 | Bấm **Xóa** một đợt chưa có phiếu chi | Xoá được; trạng thái phiếu và công nợ tụt theo |
| 7.5.3 | Lập phiếu chi cho một đợt (mục 9), rồi quay lại bấm Sửa/Xoá đợt đó | ❌ Không có nút — hiện pill **"Đã chi — khoá"** |

> **Vì sao khoá:** tiền đã ra rồi thì không được đổi số hàng dưới chân nó. Muốn sửa thì **huỷ phiếu
> chi trước**.

### 7.6 Một hoá đơn phủ nhiều đợt

Ca thật: NCC giao 3 đợt rồi mới xuất **một** hoá đơn chung.

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 7.6.1 | Đơn có 1 đợt — tìm nút **Gán hóa đơn cho nhiều đợt** | Không có (1 đợt thì sửa thẳng đợt nhanh hơn) |
| 7.6.2 | Đơn có ≥2 đợt — bấm **Gán hóa đơn cho nhiều đợt** | Hộp mở ra, tick sẵn các đợt **chưa có hoá đơn** |
| 7.6.3 | Chọn cả 3 đợt, gõ số `HĐ-0001` + ngày, lưu | Cả 3 đợt hiện **cùng** số `HĐ-0001` |
| 7.6.4 | Chọn ngày hoá đơn **ở tương lai** | ❌ Bị chặn |

### 7.7 Đóng đơn — NCC giao thiếu rồi thôi

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 7.7.1 | Phiếu đang **Giao một phần** (đặt 1.000, mới giao 700). Bấm **Đóng đơn (không giao nữa)** | Hộp mở, **bắt buộc ghi lý do** |
| 7.7.2 | Để trống lý do | ❌ Bị chặn |
| 7.7.3 | Nhân viên thường bấm | ❌ Không đủ quyền — cần quyền duyệt |
| 7.7.4 | Ghi lý do, xác nhận | Phiếu → **Đã nhận**; công nợ **chốt theo số đã giao**, phần chưa giao rơi ra |
| 7.7.5 | Kiểm công nợ | Đúng bằng tổng tiền các đợt đã ghi, **không** phải giá trị đơn |
| 7.7.6 | Phiếu ở **Đã mua**, **chưa ghi đợt nào** — tìm nút Đóng đơn | ❌ Không có. Không mua nữa thì dùng **Huỷ đơn** |

> **Đóng đơn ≠ Huỷ đơn.** *Đóng đơn* dùng khi hàng đã về **một phần** rồi NCC thôi không giao —
> giữ nguyên phần đã về, chốt nợ theo đó. *Huỷ đơn* dùng khi **chưa món nào về**. Đóng một đơn
> chưa nhận gì sẽ ghi nợ nguyên giá trị đơn dù không hàng nào về, nên hệ chặn.

### 7.8 Mở lại đơn

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 7.8.1 | Phiếu **Đã nhận**, chưa có phiếu chi. Bấm **Mở lại đơn** | Bắt ghi lý do; phiếu về **Giao một phần** (còn đợt) |
| 7.8.2 | Phiếu đã có phiếu chi. Bấm **Mở lại đơn** | ❌ Bị chặn: *"Đơn đã có phiếu chi ĐÃ CHI"* |
| 7.8.3 | Huỷ phiếu chi đó rồi bấm lại | ✅ Mở lại được |

✅ **Chốt mục 7:** hàng về tới đâu nợ tới đó; tiền bám hoá đơn; tổng không vượt đơn đã duyệt.

---

## 8. Đơn KHÔNG theo dõi theo đợt (đường cũ, vẫn còn)

Đơn nhỏ giao một lần thì không ai muốn khai đợt.

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 8.1 | Phiếu ở **Đã mua**, **chưa ghi đợt nào**. Bấm **Đã nhận** | Mở hộp khai số thực nhận từng dòng, điền sẵn = số đặt |
| 8.2 | Hàng về đủ → xác nhận luôn | Không phải gõ gì |
| 8.3 | Khai **thiếu** (đặt 1.000, nhận 800) | Nhận; công nợ = 1.760.000 (theo số thực nhận) |
| 8.4 | Khai **nhiều hơn** số đặt | ❌ Bị chặn |
| 8.5 | Phiếu **đã có đợt giao**, tìm nút **Đã nhận** | ❌ Không có — đơn theo đợt thì trạng thái tự suy |
| 8.6 | Phiếu đã có đợt giao, tìm **Sửa số nhận** | ❌ Không có — sửa ở đúng đợt giao |

✅ **Chốt mục 8:** đơn cũ / đơn đơn giản vẫn chạy y như trước, không ai bị ép khai đợt.

---

## 9. ⭐ Kế toán lập phiếu chi — KHÔNG CÒN "Chờ chi"

**Vào:** `Kế toán → Kế toán thu mua → Đơn mua hàng`

### 9.1 Vào màn

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 9.1.1 | Mở màn | Hiện tất cả trạng thái; **không** có đơn *Nháp* |
| 9.1.2 | Đăng nhập kế toán (không có quyền duyệt) | Thấy danh sách, **không** thấy nút Duyệt |
| 9.1.3 | Bấm **Lập phiếu chi** trên đơn **chưa duyệt** | ❌ Không lập được |
| 9.1.4 | Đơn của NCC đang **vượt hạn mức** | Hiện băng cảnh báo mềm; **vẫn lập được phiếu** |

### 9.2 ⭐ Loại phiếu: Đặt cọc hay Thanh toán

Form phiếu chi có ô **Loại phiếu** với hai lựa chọn — đây là thứ **mới**, chọn sai là số tiền tối đa
sẽ khác hẳn.

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 9.2.1 | Đơn **chưa giao đợt nào**. Chọn **Thanh toán** | Không chọn được / bị vô hiệu — chưa có đợt nào để trả |
| 9.2.2 | Chọn **Đặt cọc** trên đơn **CÓ** khai cọc dự kiến 500.000 | Ô số tiền điền sẵn **500.000** |
| 9.2.2b | Chọn **Đặt cọc** trên đơn **KHÔNG** khai cọc dự kiến | Điền sẵn **nửa giá trị đơn** (đơn 2.200.000 → 1.100.000) |
| 9.2.2c | Sửa số tiền thành số khác | ✅ Sửa được — điền sẵn chỉ là gợi ý |
| 9.2.2d | Đơn **đã có** phiếu Đặt cọc, chọn lại **Đặt cọc** | Hiện băng vàng liệt kê phiếu cọc đã lập + tổng, ghi rõ *"đây là phiếu cọc thứ 2"* |
| 9.2.2e | Vẫn bấm **Lập chứng từ** | ✅ **Vẫn lập được** — chỉ cảnh báo. Ứng thêm là ca có thật, và mỗi lần tiền rời két phải có chứng từ riêng |
| 9.2.3 | Lập phiếu cọc 600.000, lưu | Phiếu ra ngay trạng thái **Đã chi** — không còn bước xác nhận |
| 9.2.4 | Tìm nút **Xác nhận đã chi** ở màn Phiếu chi | ❌ Không còn — đã bỏ hẳn |
| 9.2.5 | Đơn **đã có đợt giao**. Chọn **Thanh toán** | Hiện ô **chọn đợt giao**; số tiền điền sẵn = **công nợ hiện tại** |
| 9.2.6 | Chọn Thanh toán nhưng **không chọn đợt** | ❌ Bị chặn: *"phải chọn đợt giao"* |
| 9.2.7 | Thanh toán **vượt còn nợ CỦA ĐỢT đang chọn** | ❌ Bị chặn, báo rõ *"cho đợt N"* + số tối đa |
| 9.2.7b | Chọn Đợt 2 rồi gõ số của **cả đơn** (vẫn trong công nợ tổng) | ❌ **Bị chặn** — trả nhiều đợt thì lập nhiều phiếu |
| 9.2.7c | Đổi sang đợt khác trong ô chọn | Số tiền **điền lại** theo trần của đợt mới |
| 9.2.8 | Đặt cọc **vượt giá trị đơn** | ❌ Bị chặn |

> **Hai trần khác nhau có chủ ý:**
> - **Đặt cọc** = chi khi hàng **chưa về** ⇒ trần theo **giá trị đơn**.
> - **Thanh toán** = trả cho hàng **đã về** ⇒ trần theo **công nợ đã phát sinh**.
>
> Trả tiền cho hàng chưa về mà gọi là "thanh toán" thì màn công nợ báo nợ ít hơn số phiếu chi đã
> viết — hai con số chửi nhau, không biết tin số nào.

### 9.3 Ngày tháng

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 9.3.1 | Chọn **Ngày chứng từ ở tương lai** | ❌ Bị chặn |
| 9.3.2 | Chọn **Ngày chứng từ ở quá khứ** (hoá đơn về muộn) | ✅ **Cho phép** |
| 9.3.3 | Chọn **Ngày hoá đơn ở tương lai** | ❌ Bị chặn |
| 9.3.4 | Tìm ô **Hạn trả tiền** (bắt buộc ở bản cũ) | ❌ Không còn — hạn trả đã chuyển sang đợt giao |

> **Vì sao cho ngày quá khứ:** chi tiêu phát sinh 28/7 mà hoá đơn về 5/8 thì phiếu phải mang ngày
> **28/7** mới vào đúng kỳ kế toán.

### 9.4 UNC (chuyển khoản)

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 9.4.1 | Khai 1 tài khoản công ty + 1 tài khoản NCC (`Kế toán → Tài khoản ngân hàng`) | Lưu được |
| 9.4.2 | Lập phiếu loại **Chuyển khoản**, chọn 2 tài khoản | Lưu được, mã bắt đầu bằng `UNC-` |
| 9.4.3 | Nhìn **số chứng từ** (doc_no) của phiếu tiền mặt và UNC | Chung một bộ đếm: `PC00001`, `PC00002`… |
| 9.4.4 | Chọn tài khoản NCC **không thuộc** NCC của đơn | ❌ Bị chặn |

### 9.5 Sửa / huỷ phiếu chi

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 9.5.1 | Tìm nút **Sửa** trên một phiếu đã lập | ❌ Không còn. Phiếu phát hành ra là tiền đã rời két |
| 9.5.2 | Huỷ một phiếu | Bắt ghi lý do; huỷ xong công nợ **quay lại**, không mất |
| 9.5.3 | Phiếu đã có **phiếu thu** gắn vào — thử sửa hoặc huỷ | ❌ Bị chặn, báo huỷ phiếu thu trước |
| 9.5.4 | Đính kèm ảnh hoá đơn vào phiếu chi | Tải lên được, kể cả sau khi phiếu đã chi |

✅ **Chốt mục 9:** lập phiếu chi **là** hành vi chi tiền; hai loại phiếu có hai trần khác nhau.

---

## 10. ⭐⭐ Màn Công nợ phải trả

**Vào:** `Kế toán → Kế toán thu mua → Công nợ phải trả`

### 10.1 Hiểu các con số trước khi test

Một khoản tiền đi qua **ba** chặng (bản cũ có bốn — chặng *Chờ chi* đã bị bỏ):

| Chặng | Chuyện gì xảy ra | Nằm ở |
|---|---|---|
| 1 | Duyệt đơn, chưa giao đợt nào | *chưa nằm ở đâu* — chưa nợ ai |
| 2 | Ghi đợt giao → hàng đã về | **Còn nợ** (chia tiếp thành *Quá hạn* / *Chưa tới hạn*) |
| 3 | Lập phiếu chi → tiền rời két | **Đã trả** |

**Công thức:** `Còn nợ = tổng tiền các đợt đã giao − (đã chi − đã thu về)`

Phiếu **Đặt cọc** cũng là một phiếu chi, nên cọc **tự khấu trừ ngay từ đợt giao đầu tiên** — đúng
câu "nợ − cọc − đã trả".

### 10.2 Dải số đầu màn

| Ô | Nghĩa |
|---|---|
| **Còn nợ** | Tất cả đang nợ NCC |
| **Quá hạn** | Phần đã quá hạn trả (theo hạn của **từng đợt giao**) |
| **Đã trả (3 tháng)** | Tiền **đã thật sự rời két** trong 3 tháng gần nhất |
| **Vượt hạn mức** | Số NCC đang nợ quá hạn mức đã khai |

### 10.3 Bảng theo nhà cung cấp

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 10.3.1 | Ghi đợt giao, **chưa lập phiếu chi** | NCC hiện, **Còn nợ** = tiền đợt |
| 10.3.2 | Lập phiếu chi trả đúng số đó | **Còn nợ về 0**, **Đã trả** tăng đúng bằng số đó |
| 10.3.3 | Trả **một phần** (nợ 880.000, chi 500.000) | Vẫn còn nợ **380.000** — không được biến mất |
| 10.3.4 | **Huỷ** phiếu chi | Nợ **quay lại**, không mất |
| 10.3.5 | Duyệt đơn nhưng **chưa giao đợt nào** | NCC đó **không** hiện trên màn công nợ |
| 10.3.6 | NCC A (hạn mức 3.000.000) đang nợ 4.000.000 | Có pill đỏ **Vượt hạn mức**, kèm số vượt |
| 10.3.7 | Trong lúc đang vượt hạn mức, lập đơn mới + duyệt cho NCC A | ✅ **Vẫn làm được** — chỉ cảnh báo, không chặn |

### 10.4 ⭐ Quá hạn tính theo ĐỢT GIAO

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 10.4.1 | NCC A (số ngày cho nợ = **30**). Ghi đợt giao **hôm nay** | Cột **Hạn trả** của đợt = hôm nay + 30 ngày |
| 10.4.2 | Ghi một đợt với **ngày giao lùi 40 ngày** | Hạn trả đã qua ⇒ đợt vào cột **Quá hạn**, hiện *quá N ngày* |
| 10.4.3 | Tìm ô **Hạn trả** trong form ghi đợt | ❌ Không có — hạn trả luôn để hệ suy, không gõ tay |
| 10.4.5 | NCC B (**để trống** số ngày cho nợ). Ghi đợt giao | Đợt hiện badge **Chưa đặt hạn**, **không** vào cột Quá hạn, và bị đẩy lên **ĐẦU** danh sách |

> **Bước 10.4.5 quan trọng.** Đợt không có hạn thì không bao giờ vào cột *Quá hạn* — nếu nó cũng
> chìm xuống cuối danh sách thì đó là một món nợ **không ai canh**. Vì thế nó phải nổi lên đầu kèm
> badge. Thấy nó nằm cuối danh sách là **lỗi**, báo lại.
>
> ⚠️ Vì form ghi đợt **không còn ô Hạn trả**, đường DUY NHẤT để đợt có hạn là khai **Số ngày cho
> nợ** ở hồ sơ nhà cung cấp (mục 1). NCC nào chưa khai thì **mọi** đợt của họ đều nằm ngoài cột
> Quá hạn — đó là lý do badge "Chưa đặt hạn" phải đập vào mắt.

### 10.5 Bấm vào NCC — hai khối

| Khối | Nội dung |
|---|---|
| **Còn nợ** | Từng **ĐỢT GIAO** chưa trả hết: `Đơn · Đợt · Ngày giao · Hóa đơn · Hạn trả · Giá trị · Đã trả · Còn nợ`, rồi **dòng riêng** *Đặt cọc / ứng trước cho cả đơn* và *Còn nợ sau khi trừ cọc* |
| **Đã trả (3 tháng)** | Từng **lần trả**: ngày · phiếu · loại (đặt cọc/thanh toán) · đợt · hoá đơn · số tiền |

#### 10.5b ⭐ Cọc là cọc CẢ ĐƠN — cột riêng, không lẫn vào "Đã trả"

Drawer gom khoản nợ **theo từng ĐƠN MUA**: mỗi đơn một khối, đầu khối ghi mã đơn · cọc của chính
đơn đó · tổng còn nợ · nút *Lập phiếu chi*. Bảng bên trong có **8 cột**, trong đó `Đã trả` và
`Cọc bù` là hai cột **khác nhau**.

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 10.5b.1 | Lập phiếu **Đặt cọc 100.000**, rồi ghi đợt 1 trị giá 1.000.000 | Đợt 1: `Giá trị 1.000.000 · Đã trả **0** · Cọc bù **100.000** · Còn nợ **900.000**` |
| 10.5b.2 | Nhìn đầu khối đơn | `PMH-… · cọc 100.000 · đã bù 100.000 · còn nợ 900.000` |
| 10.5b.3 | Lập tiếp phiếu **Thanh toán 500.000**, chọn **đợt 1** | Đợt 1: `Đã trả 500.000 · Cọc bù 100.000 · Còn nợ 400.000` |
| 10.5b.4 | Trả nốt **400.000** cho đợt 1 | Đợt 1 **biến mất** khỏi danh sách còn nợ; tổng về **0đ** |
| 10.5b.5 | Có **2 nhà cung cấp × nhiều đơn** — mở một NCC nhiều đơn | Mỗi đơn một khối riêng, cọc của đơn nào nằm ở đơn đó |

> **Vì sao `Đã trả` và `Cọc bù` tách đôi:** cột *Đã trả* phải khớp **sao kê NCC theo từng đợt** nên
> chỉ được đếm tiền trả đích danh đợt đó. Cọc là thoả thuận ở mức **đơn hàng** — gộp vào là bảng
> nói dối. Nhưng cột **Còn nợ** thì trừ **cả hai**: cọc đã trả rồi, để đợt báo nợ kèm nút *Lập phiếu
> chi* là mời kế toán trả lần thứ hai (lỗi chủ bắt được 07/08/2026).

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 10.5.1 | Cộng tay các dòng khối *Còn nợ* rồi **trừ dòng cọc** | Đúng bằng cột **Còn nợ** ngoài bảng |
| 10.5.2 | Cộng tay khối *Đã trả* | Đúng bằng cột **Đã trả** ngoài bảng |
| 10.5.3 | Xem đầu drawer | Hiện **hạn mức / đã nợ / còn được nợ** của NCC |
| 10.5.4 | Đơn **không theo đợt** (mục 8) | Hiện một dòng ở mức **PHIẾU**, badge *Đơn không theo đợt* |
| 10.5.5 | Phiếu chi chưa đính kèm chứng từ | Có chữ nhắc *"chưa có chứng từ"* (chỉ nhắc, không chặn) |

### 10.6 Làm sao biết đã trả hết

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 10.6.1 | Trả hết một NCC | Họ **vẫn nằm trên bảng**: Còn nợ **0đ**, cột *Đã trả* có số |
| 10.6.2 | Không nợ ai cả | Bảng ghi rõ "không còn nợ…" kèm ngày giờ chốt |
| 10.6.3 | Gõ tên NCC đã trả hết từ lâu vào ô tìm | Vẫn ra dòng của họ |
| 10.6.4 | Mở NCC đó, khối *Đã trả* rỗng → bấm **Xem lịch sử cũ hơn** | Hiện lại các lần chi ngoài 3 tháng |

> **Kỳ 3 tháng chỉ cắt phần ĐÃ TRẢ.** Nợ chưa trả **không bao giờ rơi** — đơn nợ từ năm ngoái hôm
> nay vẫn hiện đủ.

### 10.7 🔴 Khi hệ thống lỗi — quan trọng nhất

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 10.7.1 | Tắt backend rồi mở màn công nợ | Các ô hiện **`—`**, có **banner đỏ** báo lỗi |
| 10.7.2 | | ❌ **Tuyệt đối không được hiện `0đ`** |

> *"0đ"* và *"hết nợ"* nhìn giống hệt nhau. Màn hỏng mà vẫn hiện 0đ thì người xem tin là đã trả hết
> trong khi đang nợ.

✅ **Chốt mục 10:** mọi con số suy từ chứng từ, không ai gõ tay; im lặng **không bao giờ** được hiểu
là hết nợ.

---

## 11. ⭐ Phiếu thu — nộp lại tiền thừa (ca "nợ ảo")

Ca thật: tạm ứng cho nhân viên đi mua 10 triệu, mua hết 8,5 triệu, nộp lại 1,5 triệu.

**Vào:** `Kế toán → Phiếu chi` → mở phiếu đã chi → **Lập phiếu thu**

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 11.1 | Đơn 11.000.000. Lập phiếu chi **Đặt cọc 10.000.000** | Ra phiếu **Đã chi** |
| 11.2 | Ghi đợt giao trị giá **8.500.000**, rồi **Đóng đơn** | Công nợ = 8.500.000 − 10.000.000 → **0đ** (đã chi thừa) |
| 11.3 | Lập **phiếu thu 1.500.000** trên phiếu chi đó | Lập được |
| 11.4 | Bấm **Đã thu** | Trạng thái *Đã thu* |
| 11.5 | Xem lại phiếu mua | **Đã chi 10.000.000 · Đã thu 1.500.000 · Còn nợ 0đ** |
| 11.6 | Xem màn Công nợ | NCC đó **không còn nợ** |
| 11.7 | Thử lập phiếu thu **vượt** số đã chi | ❌ Bị chặn |
| 11.8 | Thử lập phiếu thu trên phiếu chi **đã huỷ** | ❌ Bị chặn |

> **Bước 11.5–11.6 là chốt.** Bản trước ra *"còn nợ 1.500.000"* ở đây — tiền đã về két mà bảng vẫn
> báo nợ NCC. Nay đo nợ theo **hàng đã về** nên ra đúng **0**.

✅ **Chốt mục 11:** tiền về két thì không được còn nợ ma.

---

## 12. Phạm vi nhìn — ai thấy gì

| # | Đăng nhập bằng | Vào | Kết quả mong đợi |
|---|---|---|---|
| 12.1 | Nhân viên mua hàng | `Thu mua → Mua hàng` | Chỉ thấy **phiếu mình lập** |
| 12.2 | Trưởng bộ phận mua hàng | `Thu mua → Mua hàng` | Thấy phiếu **cả bộ phận** |
| 12.3 | Giám đốc | `Thu mua → Mua hàng` | Thấy **tất cả** |
| 12.4 | Nhân viên mua hàng | `Thu mua → Yêu cầu mua hàng` | Thấy yêu cầu của **mọi phòng ban** |
| 12.5 | Kế toán | `Kế toán → Đơn mua hàng` | Thấy **tất cả** đơn |
| 12.6 | Người không có quyền kế toán | Công nợ phải trả | ❌ Báo không có quyền |
| 12.7 | Người không có quyền thu mua | Mở link ảnh hợp đồng của phiếu mua | ❌ Báo không có quyền |

> Phân biệt **12.1** với **12.4**: *phiếu mua* là việc riêng của người lập, còn *yêu cầu mua hàng*
> là hộp việc chung của cả bộ phận thu mua.
>
> **12.7 là chốt bảo mật** — hợp đồng NCC không được để ai đăng nhập cũng đọc.

---

## 12c. ⭐ MỚI — Nhập / xuất Excel bảng giá vật tư

**Vào:** `Thu mua → Nhà cung cấp` → mở một NCC → tab **Bảng giá vật tư**

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 12c.1 | Bấm **Tải mẫu** | Tải về `mau-vat-tu-nha-cung-cap.xlsx`, mở lên có tiêu đề + 2 dòng ví dụ + dòng nhắc luật |
| 12c.2 | Bấm **Xuất Excel** | File chứa **đúng** danh mục của NCC đang mở |
| 12c.3 | ⭐ Sửa vài giá trong file vừa xuất rồi **Nhập Excel** chính file đó | Các dòng cũ **được cập nhật giá**, KHÔNG đẻ dòng thứ hai |
| 12c.4 | Thêm 2 dòng mới vào file rồi nhập | Danh mục cũ **còn nguyên**, 2 dòng mới nối thêm vào cuối |
| 12c.5 | ⭐ Nhìn dòng chữ dưới nút sau khi nhập | Có câu **"Chưa lưu — … bấm Lưu nhà cung cấp"** |
| 12c.6 | ⭐ Đóng drawer **không lưu**, mở lại NCC đó | Bảng giá **như cũ** — phần vừa nhập không vào sổ. Đúng ý đồ |
| 12c.7 | Nhập lại rồi bấm **Lưu nhà cung cấp** → mở lại | Lúc này bảng giá mới **đã vào sổ** |
| 12c.8 | Nhập file có dòng thiếu tên / thiếu ĐVT / đơn giá là chữ | Dòng lành **vẫn vào**, dòng hỏng liệt kê kèm **số dòng Excel** đúng như khi mở file |
| 12c.9 | Nhập file có 2 dòng **cùng tên + cùng ĐVT** | Chỉ còn 1 dòng, lấy giá của **dòng dưới**, có báo trùng |
| 12c.10 | Nhập file **>500 dòng** | ❌ Bị chặn, báo rõ số dòng và trần 500 |
| 12c.11 | Nhập một file **không phải .xlsx** (đổi tên .txt) | ❌ Bị chặn, báo cần file Excel |
| 12c.12 | Đơn giá gõ `2.200` hoặc `4,400`, VAT gõ `10%` | Vẫn nhận đúng 2200 · 4400 · VAT 10 |
| 12c.13 | Tài khoản chỉ có quyền **xem** thu mua | Thấy *Tải mẫu* / *Xuất Excel*; bấm *Nhập Excel* thì bị từ chối |

✅ **Chốt mục 12c:** xuất → sửa trong Excel → nhập lại là một vòng khép kín, không mất dòng nào.

---

## 12b. ⭐ MỚI — Lịch sử trạng thái

**Vào:** `Thu mua → Yêu cầu mua hàng` **và** `Thu mua → Mua hàng` · mở chi tiết một phiếu đã đi
qua vài bậc

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 12b.1 | Kéo xuống cuối drawer chi tiết | Có khối **Lịch sử trạng thái**, **mới nhất trên cùng** |
| 12b.2 | Đọc một dòng bất kỳ | Đủ ba thứ: *từ trạng thái → tới trạng thái*, **thời điểm**, **ai** |
| 12b.3 | Dòng dưới cùng | Là *Lập phiếu · Nháp* (hoặc *Chờ Thu mua xử lý*) — mốc phiếu sinh ra |
| 12b.4 | ⭐ Duyệt PMH ⇒ YCMH tự đổi sang *Đang mua*. Mở lịch sử của **YCMH** | Dòng đó ghi **"Hệ thống tự cập nhật"**, KHÔNG gán tên người nào |
| 12b.5 | Từ chối / huỷ một phiếu **có ghi lý do**, mở lại chi tiết | Lý do hiện thành **dòng riêng có vạch đỏ** ở đầu phiếu, VÀ nằm trong dòng lịch sử tương ứng |
| 12b.6 | ⭐ Kiểm chỗ hay hỏng nhất: nội dung người lập gõ ban đầu | **Còn nguyên** — lý do từ chối KHÔNG đè lên nội dung (lỗi cũ trước 07/08/2026) |
| 12b.7 | Mở phiếu **CŨ** (lập trước 07/08/2026) | Khối lịch sử báo *chưa ghi nhận đổi trạng thái nào* — đúng, không backfill |

✅ **Chốt mục 12b:** nhìn lịch sử là biết phiếu đã đi qua đâu, ai đẩy, máy hay người.

---

## 13. Bảng ghi kết quả

| Mục | Nội dung | ✅/❌ | Ghi chú khi sai |
|---|---|---|---|
| 1 | Hạn mức + số ngày cho nợ NCC | | |
| 2 | Bộ phận gửi yêu cầu | | |
| 3 | Tách phiếu theo NCC | | |
| 4 | Trạng thái khi hai phiếu lệch nhau | | |
| 4.7 | Phiếu bị từ chối | | |
| 5 | Tình trạng từng sản phẩm | | |
| 6 | Hợp đồng + cọc dự kiến | | |
| 7.1–7.2 | Ghi đợt giao + tiền theo hoá đơn | | |
| 7.3–7.4 | Hai trần (tiền / số lượng) | | |
| 7.5–7.6 | Sửa-xoá đợt · gán hoá đơn chung | | |
| 7.7–7.8 | Đóng đơn · Mở lại đơn | | |
| 8 | Đơn không theo dõi theo đợt | | |
| 9 | Phiếu chi (đặt cọc / thanh toán) | | |
| 10 | Công nợ phải trả | | |
| 11 | Phiếu thu — nộp lại tiền thừa | | |
| 12 | Phạm vi nhìn | | |
| 12b | Lịch sử trạng thái + ô nội dung gộp | | |
| 12c | Nhập / xuất Excel bảng giá vật tư | | |

---

## Phụ lục — mấy chỗ hay tưởng là lỗi mà không phải

| Hiện tượng | Có phải lỗi? | Giải thích |
|---|---|---|
| Phiếu chi vừa lập đã là **Đã chi** | **Không** | Lập phiếu chi = tiền đã ra. Đây là thay đổi của bản này |
| Không tìm thấy nút **Xác nhận đã chi** | **Không** | Đã bỏ hẳn |
| Không thấy cột **Chờ chi** ở công nợ | **Không** | Đã bỏ — không còn khoảng giữa "ghi sổ" và "đã trả" |
| Không thấy ô **Hạn trả** trên phiếu chi | **Không** | Hạn trả chuyển sang đợt giao |
| Không có nút **Sửa** phiếu chi | **Không** | Chứng từ đã phát hành thì không sửa; huỷ rồi lập lại |
| Form ghi đợt **không có ô nhập tiền** | **Không** | Tiền = số lượng × đơn giá, máy tính |
| Form ghi đợt **không có ô Hạn trả** | **Không** | Hạn = ngày giao + số ngày cho nợ của NCC, hệ tự suy |
| Form ghi đợt **không có cột tiền theo dòng** | **Không** | Hoá đơn ghi một số tổng; tiền của đợt là ô *Số tiền theo hóa đơn* |
| Ảnh trong hộp ghi đợt ghi *"chờ tải lên"* | **Không** | Đợt chưa lưu thì chưa có chỗ gắn file; lưu xong ảnh mới lên |
| Đợt giao hiện tiền **khác** giá trị đơn | **Không** | Đợt chỉ tính phần đã nhận, không phải cả đơn |
| Không lập được phiếu **Thanh toán** khi chưa giao đợt | **Không** | Chưa có nợ. Dùng loại **Đặt cọc** |
| Đơn đã duyệt không hiện ở công nợ | **Không** | Chưa giao đợt nào thì chưa nợ |
| Cọc dự kiến không làm giảm công nợ | **Không** | Nó chỉ để nhắc; cọc thật là phiếu chi |
| Cọc dự kiến **không sửa được** sau khi duyệt | **Không** | Là con số người duyệt đã đồng ý |
| Đợt 1 hiện *Đã trả 0* dù đã đặt cọc | **Không** | Cọc nằm ở cột **Cọc bù** riêng; *Đã trả* chỉ đếm tiền trả đích danh đợt |
| Lập được phiếu Đặt cọc thứ hai cho cùng một đơn | **Không** | Chỉ cảnh báo — mỗi lần chi tiền phải có một chứng từ riêng |
| Ngoài bảng ghi *Đã giao* khác *Tổng PMH* | **Không** | Đã giao = tổng tiền HOÁ ĐƠN các đợt; Tổng PMH = giá trị đơn đặt |
| Vượt hạn mức mà vẫn duyệt được đơn | **Không** | Cảnh báo mềm, cố ý không chặn |
| Đợt của NCC chưa khai số ngày cho nợ **không** vào Quá hạn | **Không** | Không có hạn thì lấy gì mà so — nhưng nó phải nổi lên **đầu** danh sách |
| Không sửa được đợt đã có phiếu chi | **Không** | Tiền đã ra thì không đổi số hàng dưới chân nó |
| Màn công nợ hiện `—` thay vì `0đ` | **Không** | Đang lỗi tải; `—` nghĩa là *chưa biết* |
| Màn công nợ hiện `0đ` **trong khi đang có nợ** | 🔴 **CÓ** | Báo ngay |
| Giao 1 đợt mà công nợ vẫn **0đ** | 🔴 **CÓ** | Báo ngay — đây đúng là lỗi bản này sinh ra để sửa |
| Đơn trả một phần biến mất khỏi công nợ | 🔴 **CÓ** | Báo ngay |
| Đợt **Chưa đặt hạn** nằm cuối danh sách | 🔴 **CÓ** | Báo ngay — nó phải nổi lên đầu |
| Tiền cọc bị cộng vào cột *Đã trả* của một đợt | 🔴 **CÓ** | Báo ngay — cọc phải ở cột *Cọc bù* |
| Đợt đã đủ tiền (kể cả cọc) mà vẫn báo *Còn nợ* / vẫn có nút *Lập phiếu chi* | 🔴 **CÓ** | Báo ngay — mời trả hai lần |
| Nhiều đơn mà các đợt đổ lẫn vào một bảng, không tách theo đơn | 🔴 **CÓ** | Báo ngay |
| Kế toán không thấy cọc dự kiến ở màn Đơn mua hàng | 🔴 **CÓ** | Báo ngay |
| Tổng các đợt **vượt** giá trị đơn mà vẫn lưu được | 🔴 **CÓ** | Báo ngay |
| Ứng trước rồi nộp lại tiền thừa mà vẫn báo còn nợ | 🔴 **CÓ** | Báo ngay — đây là "nợ ảo" đã sửa |

---

## Nếu màn không đúng như tài liệu

1. **Backend đã restart chưa?** Sửa xong mà chưa restart thì màn chạy bản cũ.
2. **Có mấy bản đang chạy?** `netstat -ano | findstr :8000` phải ra đúng một dòng.
3. **Trình duyệt còn cache bản cũ?** Ctrl+F5.

Vẫn sai thì ghi lại **số hiệu bước**, chụp màn hình, và nói rõ đang đăng nhập bằng vai nào.
