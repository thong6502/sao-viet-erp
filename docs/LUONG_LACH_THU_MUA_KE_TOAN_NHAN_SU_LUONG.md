# Đọc hiểu hệ thống — Thu mua → Kế toán · Nhân sự → Lương

Tài liệu này để **hiểu hệ thống nghĩ thế nào**, không phải để bấm theo.

- Cần biết **bấm ở đâu, điền gì** → `HUONG_DAN_SU_DUNG_NHAN_SU_THU_MUA_KE_TOAN.md`
- Cần **kiểm thử** → `HUONG_DAN_TEST_THU_MUA_KE_TOAN.md` và `HUONG_DAN_TEST_NHAN_SU_LUONG.md`
- Cần hiểu **vì sao nó làm vậy** → tài liệu này

---

# PHẦN I — BỐN NGUYÊN TẮC CHUNG

Cả hai luồng đều dựng trên cùng bốn nguyên tắc. Nắm được bốn cái này thì đọc chỗ nào cũng hiểu.

## 1. Có hai loại số: **CHỨNG TỪ** và **SỐ SUY RA**

**Chứng từ** là thứ người ta lập ra và ký: yêu cầu mua hàng, phiếu mua hàng, phiếu chi, bảng lương.
Nó nằm trong kho dữ liệu, sửa được, có người chịu trách nhiệm.

**Số suy ra** là kết quả cộng trừ từ chứng từ, **không ai gõ tay được**: công nợ phải trả, trạng
thái yêu cầu mua hàng, tổng công tháng.

> Vì sao phân biệt: số nào gõ tay được thì sớm muộn có hai nguồn, và hai nguồn thì lệch nhau. Lệch
> tiền là loại lệch không ai phát hiện cho tới lúc ngồi đối chiếu với bên ngoài.

Ví dụ rõ nhất: **màn Công nợ phải trả không có bảng dữ liệu nào**. Toàn bộ con số trên đó được cộng
lại lúc mở màn. Muốn một món nợ biến mất chỉ có hai đường: lập phiếu chi rồi chi, hoặc huỷ đơn.

## 2. Tách vai: **ai đề xuất thì không được đồng ý**

| Việc | Ai làm | Ai KHÔNG được làm |
|---|---|---|
| Xin mua hàng | Bộ phận cần hàng | |
| Lập phiếu mua | Thu mua | |
| **Duyệt** phiếu mua | Giám đốc / người được trao quyền | **Người lập phiếu** — kể cả giám đốc tự lập |
| Lập phiếu chi | Kế toán | |
| Xác nhận tiền ra | Người giữ quỹ | |

Chốt "người lập không tự duyệt" nằm ở **tầng nghiệp vụ**, không phải chỉ ở phân quyền. Lý do: phân
quyền là cấu hình — ai vào màn Phân quyền bật lại cũng được mà không ai hay. Chốt ở tầng nghiệp vụ
thì bật quyền cũng không lách được.

## 3. Trạng thái là **SUY RA**, không phải gán

Một yêu cầu mua hàng có thể tách thành nhiều phiếu (mỗi nhà cung cấp một phiếu). Các phiếu chạy
lệch nhịp: phiếu giấy đã về, phiếu băng keo còn chờ duyệt.

Trạng thái yêu cầu **luôn lấy theo phần chậm nhất**:

```
Chờ mua  <  Chờ duyệt  <  Đang mua  <  Xong
```

Duyệt một phiếu trong hai ⇒ yêu cầu **vẫn Chờ duyệt**. Chỉ khi mọi phần đã về hàng mới **Xong**.

> **Vì sao lấy chậm nhất:** báo bi quan thì cùng lắm bộ phận đi hỏi. Báo lạc quan thì họ ngồi chờ
> hàng không bao giờ tới.

Phiếu **bị từ chối** hoặc **đã huỷ** tính là bậc thấp nhất — phần hàng đó chưa ai mua được, nên
yêu cầu phải quay về hàng chờ để thu mua lập phiếu khác.

## 4. Im lặng **không** có nghĩa là không có gì

Màn hình lỗi và màn hình "hết sạch" nhìn giống hệt nhau nếu không cẩn thận. Nguyên tắc:

- Chưa tính được ⇒ hiện **`—`**
- Đã tính ra và bằng không ⇒ hiện **`0đ`** kèm câu khẳng định *"Không còn nợ ai — chốt lúc …"*

Chuyện này đã xảy ra thật: có lúc API chết mà màn vẫn đổ ra "0đ / chưa nợ ai", suýt làm người xem
tin là đã trả hết.

---

# PHẦN II — THU MUA → KẾ TOÁN

## 2.1. Năm chứng từ, ai đẻ ra ai

```
   Bộ phận                Thu mua              Giám đốc          Kế toán
      │                      │                     │                │
      ▼                      │                     │                │
 ① YÊU CẦU MUA HÀNG ────────►│                     │                │
   (YCMH)                    ▼                     │                │
                        ② PHIẾU MUA HÀNG ─────────►│                │
                           (PMH)              duyệt/từ chối         │
                              │                     │               ▼
                        ③ nhận hàng                 └──────► ④ PHIẾU CHI
                        (khai số thực nhận)                        │
                              │                                    ▼
                              └────────────────► ⑤ CÔNG NỢ ◄── xác nhận Đã chi
                                                (số suy ra)
```

| # | Chứng từ | Ai lập | Ý nghĩa |
|---|---|---|---|
| ① | **Yêu cầu mua hàng** | Bộ phận cần hàng | *"Tôi cần thứ này"* |
| ② | **Phiếu mua hàng** | Thu mua | *"Tôi mua của nhà cung cấp này, giá này"* |
| ③ | **Nhận hàng** | Thu mua | *"Hàng đã về, thực nhận bao nhiêu"* |
| ④ | **Phiếu chi** | Kế toán | *"Trả bao nhiêu, hạn nào"* |
| ⑤ | **Công nợ** | *không ai lập* | Cộng trừ ra |

## 2.2. Một đồng tiền đi qua bốn chặng

Đây là cách dễ nhất để hiểu màn Công nợ:

| Chặng | Chuyện gì | Nằm ở cột |
|---|---|---|
| 1 | Đơn đã duyệt, chờ hàng về | *chưa ở đâu cả* — **chưa nợ ai** |
| 2 | Hàng về rồi, kế toán chưa lập phiếu | **Chưa vào sổ** |
| 3 | Lập phiếu chi rồi, tiền chưa ra | **Chờ chi** |
| 4 | Bấm *Đã chi*, tiền rời két | **Đã trả** |

**Chặng 2 + 3 = Tổng còn nợ.** Chặng 4 = Đã trả.

### Vì sao chặng 1 chưa phải nợ

Đặt hàng thì chưa nợ ai. Đơn duyệt hôm nay, hai tuần nữa hàng mới về — hai tuần đó không nợ đồng
nào. Tính nợ từ lúc duyệt là đẻ ra **nợ ảo** cho hàng còn chưa rời kho nhà cung cấp.

**Mốc phát sinh nợ là NHẬN HÀNG**, không phải duyệt đơn.

### Vì sao rổ "Chưa vào sổ" quan trọng nhất

Nếu công nợ chỉ đếm phiếu chi đang chờ, thì đơn đã về hàng mà kế toán chưa kịp lập phiếu sẽ **vô
hình**. Bảng sạch bong trong khi thực tế đang nợ.

Đó là kiểu sai nguy hiểm nhất: nó **giấu nợ** chứ không phải báo sai nợ. Nhìn bảng tưởng không nợ
ai, tới lúc nhà cung cấp gọi đòi mới biết.

## 2.3. Tách phiếu theo nhà cung cấp

Một phiếu mua là **thoả thuận với MỘT nhà cung cấp**. Yêu cầu chứa hàng của hai nơi thì bắt buộc
tách thành hai phiếu.

Gọi API tạo phiếu hai lần **không làm được**: phiếu đầu giữ chỗ yêu cầu nguồn, lần hai bị chặn. Nên
có đường **tạo cả mẻ** — gán nhà cung cấp cho từng dòng, hệ nhóm lại rồi đẻ phiếu.

Máy tự gán sẵn nhà cung cấp **rẻ nhất** cho từng dòng. Thu mua chỉ phải xử lý mấy dòng có nhiều lựa
chọn.

**Thu mua không sửa được Vật tư / Đơn vị / Số lượng**, cũng không thêm/xoá dòng — đó là con số bộ
phận đã xin.

## 2.4. Số thực nhận — vì sao cần

`Số đặt` và `số thực nhận` là **hai con số khác nhau**:

| Con số | Nghĩa | Dùng ở đâu |
|---|---|---|
| Giá trị đơn | theo số **đã đặt** | in trên đơn, không đổi |
| Giá trị thực nhận | theo số **thực nhận** | **công nợ** và **trần lập phiếu chi** |

Nhà cung cấp giao 800/1000 tờ mà công nợ vẫn ghi đủ 1000 thì **kế toán chi thừa**. Nên khi bấm *Đã
nhận hàng*, hệ mở hộp khai số thực nhận — ô đã điền sẵn bằng số đặt, về đủ thì chỉ bấm Xác nhận.

Hệ quả: hàng về thiếu thì **không lập nổi phiếu chi đủ giá trị đơn**. Đó là cố ý — không siết thì
màn công nợ báo 80% trong khi phiếu chi viết 100%, hai số chửi nhau.

## 2.5. Giao nhiều đợt, mỗi đợt một hoá đơn

Phía **tiền** xử lý được: một đơn lập được nhiều phiếu chi, mỗi phiếu mang **số hoá đơn** và **hạn
trả** riêng.

| Đợt | Hoá đơn | Phiếu chi | Hạn trả |
|---|---|---|---|
| 1 | HĐ-A | PC00012 | 20/8 |
| 2 | HĐ-B | PC00019 | 30/8 |

Hai đợt quá hạn độc lập — đợt 1 trễ không kéo đợt 2 theo.

Phía **hàng** thì chưa: số thực nhận là **một con số cộng dồn**, không lưu được đợt nào về ngày nào.
Muốn có phải chờ **phiếu nhập kho**.

## 2.6. Hạn trả — và vì sao bắt buộc

Cột *Quá hạn* so `hạn trả < hôm nay`. Phiếu **không có hạn** thì không bao giờ rơi vào cột đó — kế
toán nhìn bảng thấy *Quá hạn 0đ* rồi yên tâm trong khi có phiếu trễ cả tháng.

Nên hạn trả là **bắt buộc**. Phiếu cũ lỡ tạo thiếu hạn thì gắn badge **`Chưa đặt hạn`** để lôi ra.

### Ba chốt ngày — và một chỗ cố ý KHÔNG chốt

| Chốt | Có chặn? |
|---|---|
| Ngày chứng từ ở tương lai | ❌ chặn |
| Ngày hoá đơn ở tương lai | ❌ chặn |
| Hạn trả **trước** ngày chứng từ | ❌ chặn |
| **Ngày ở quá khứ** | ✅ **cho phép** |

Quá khứ là hợp lệ và cần thiết: chi tiêu phát sinh 28/7, hoá đơn về 5/8 ⇒ phiếu phải mang ngày
**28/7** mới vào đúng kỳ kế toán. Hạn trả quá khứ cũng vậy — nhập bù khoản đã trễ thì giữ đúng ngày
để nó hiện đỏ ngay; ép sang tương lai là **làm giả nợ**.

## 2.7. Lùi lại khi bấm nhầm

Bấm nhầm *Đã nhận hàng* là đẻ ra một món nợ trên bàn kế toán. Nên có đường lùi, nhưng:

- Đòi **quyền duyệt** (không phải việc nhân viên tự quyết)
- **Bắt ghi lý do**, vào nhật ký
- **Chặn nếu đã có phiếu chi ĐÃ CHI** — tiền rời két rồi thì không quay lại khai "chưa nhận hàng"
- Tự **tính lại trạng thái yêu cầu** — quên vế này thì bộ phận vẫn thấy *Xong* trong khi phiếu đã lùi

---

# PHẦN III — NHÂN SỰ → LƯƠNG

## 3.1. Bản đồ

```
 Khai báo nền          Hằng ngày            Cuối tháng
 ─────────────         ──────────           ──────────
 Phòng ban                                   
 Ca làm việc  ──┐                            
 Lịch & ngày lễ │      Chấm công ──┐         
 Điểm chấm công │      Nghỉ phép   ├──► BẢNG CÔNG ──► CHỐT CÔNG
 Hồ sơ nhân sự ─┤      Tăng ca     │       THÁNG          │
 Cấu hình lương │      Chỉnh công ─┘                      ▼
 Lương nhân viên┘                                   BẢNG LƯƠNG
                                                    (Tính lại)
                                                         │
                                          Chốt ──► Đã chi
```

## 3.2. Chấm công: **bấm là sự thật**

Nút chấm vào/chấm ra ghi lại **mọi lần**, không hỏi tại sao, không giới hạn số lần. Ra ngoài rồi
quay lại là chuyện thường.

Việc *"được phép làm thêm bao nhiêu"* là chuyện của **phiếu tăng ca**, không phải của nút chấm công.

> **Phiếu tăng ca là GIẤY PHÉP + TRẦN**, không phải điều kiện để được tính công. Không có phiếu thì
> mất phần làm thêm, **chứ không mất công ca chính**.

## 3.3. Ba lớp phân ca

| Lớp | Ý nghĩa | Ưu tiên |
|---|---|---|
| Ca nền | ca mặc định hằng ngày của một người | thấp nhất |
| Ca theo ngày | phân riêng cho một ngày cụ thể | đè lên ca nền |
| Nghỉ | ngày đó không làm | cao nhất — ô để trống hẳn |

## 3.4. Hai lần khoá, hai ý nghĩa khác nhau

### Khoá 1 — Chốt công

Chụp Bảng công tháng thành **ảnh đóng băng**. Từ đó lương đọc ảnh này, không đọc số đang sống.

**Chặn nếu còn đơn treo** — đơn nghỉ phép, phiếu đi muộn/về sớm, yêu cầu chỉnh công chưa duyệt. Lý
do: chốt trong khi còn đơn treo thì duyệt đơn sau đó không vào được ảnh, công sai mà không ai biết.

### Khoá 2 — Chốt lương

Bảng lương đi qua **ba trạng thái**:

| Trạng thái | Nút | Nghĩa |
|---|---|---|
| **Nháp** | `↻ Tính lại` · `🔒 Chốt` | còn sửa được |
| **Đã chốt** | `Mở lại` · `💵 Đã chi` | số đã khoá, chưa phát tiền |
| **Đã chi** | `↩ Hủy đã chi` | tiền đã phát |

**Mở lại kỳ công bị chặn nếu lương đã chốt** — sai sót phải xử bằng truy lĩnh/khấu trừ kỳ sau, không
sửa ngược quá khứ.

## 3.5. Một dòng lương gồm gì

```
  Lương công          = đơn giá ngày × số công
+ Tiền cơm            = số CA THỰC LÀM × mức cơm mỗi ca
+ Phụ cấp ca          = số CA THỰC LÀM × mức phụ cấp mỗi ca
+ Tăng ca             (chỉ phần có phiếu đã duyệt)
+ Phụ trội ca đêm
─────────────────────────────────────────────
= TỔNG THU NHẬP
− Thu nhập MIỄN THUẾ  (cơm + phụ cấp ca + phụ trội tăng ca/đêm)
─────────────────────────────────────────────
= Thu nhập CHỊU THUẾ  →  tính BHXH, TNCN
```

> ⚠️ **Khoản nào cộng vào tổng thu nhập thì phải cộng cả vào phần miễn thuế.** Thiếu vế sau là người
> lao động **bị đánh thuế oan** lên khoản lẽ ra được miễn. Đây là lỗi đã từng có, đã sửa.

Cơm và phụ cấp ca tính theo **số ca thực làm**, không theo số ngày công — người làm hai ca một ngày
được hai suất.

## 3.6. Mọi con số luật đều KHAI ĐƯỢC

Không cắm cứng trong máy. Luật đổi thì sửa ở *Cấu hình lương*, không phải gọi thợ:

- Giảm trừ bản thân · giảm trừ người phụ thuộc
- Trần đóng BHXH/BHYT — đặt **0** = tắt trần
- **Ngưỡng miễn BHXH khi nghỉ không lương** — mặc định **14 ngày** theo QĐ 595/QĐ-BHXH Đ42.4; đặt
  **0** = tắt hẳn quy tắc

---

# PHẦN IV — ĐANG CÒN DỞ

Ghi ở đây để đọc tài liệu không hiểu nhầm là đã xong hết.

## Thu mua / Kế toán

| Việc | Tình trạng |
|---|---|
| **Phiếu nhập kho** | Chưa có ⇒ số thực nhận chỉ là con số cộng dồn, không lưu lịch sử từng đợt giao |
| **Đính kèm ảnh tại phiếu mua** | Chưa có; ảnh hoá đơn hiện dán ở phiếu chi |
| **Chặn cứng "không chứng từ thì không được chi"** | Hiện chỉ **cảnh báo mềm** |
| **Uỷ nhiệm chi (UNC)** | Đang **tắt**; bật lại cần màn khai tài khoản ngân hàng |
| **Vai "Kế toán"** | Không được tạo sẵn ⇒ phải tự tạo và cấp quyền ở màn Phân quyền |

## Nhân sự / Lương

| Việc | Tình trạng |
|---|---|
| **Tiền khoán** | Luôn = 0 — thiếu nguồn **sản lượng**, chờ Lệnh sản xuất |
| **Tổ tích "Làm khoán"** | Mất tăng ca mà cũng không có khoán ⇒ **thiệt hơn tổ thường**. Chữa tạm: bỏ tích |
| **Quy tắc lương theo bậc thợ** | Khai được nhưng **không bao giờ áp dụng** |
| **Ô "Loại / Bậc thợ"** | Gõ được nhưng **không ra tiền** — chỉ để xem |
| **Điều chỉnh lương ±** | Máy cộng được nhưng **không có ô nhập** trên màn |

## 🔴 Một con số chờ quyết, không phải lỗi

Mỗi ca làm việc đang mặc định **25.000đ cơm + 50.000đ phụ cấp ca** — người đủ công được cộng khoảng
**1.950.000đ/tháng**. Đây là **số mặc định trong máy, chưa ai chốt**, mà nó ra tiền thật mỗi kỳ
lương.

---

# PHẦN V — BA CÂU HỎI HAY GẶP

**"Sao yêu cầu vẫn Chờ duyệt khi tôi đã duyệt rồi?"**
Yêu cầu tách thành nhiều phiếu, còn phiếu khác chưa duyệt. Mở chi tiết yêu cầu xem **tình trạng
từng sản phẩm** để biết món nào đang kẹt.

**"Sao đơn đã duyệt mà không thấy ở Công nợ?"**
Hàng chưa về thì chưa nợ ai. Bấm *Đã nhận hàng* xong nó mới hiện.

**"Làm sao biết đã trả hết nợ một nhà cung cấp?"**
Họ **vẫn nằm trên bảng** với *Tổng còn nợ 0đ*, kèm nhãn **Đã trả hết** và số tiền đã trả làm bằng
chứng. Nếu họ đã im lặng lâu hơn 3 tháng thì gõ tên vào ô tìm — vẫn ra, và trong đó có nút **Xem
lịch sử cũ hơn**.
