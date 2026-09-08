# Kế hoạch sản xuất trọn gói cho 6 đơn DH001–DH006 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: dùng superpowers:executing-plans để chạy từng task.
> Các bước dùng cú pháp checkbox (`- [ ]`) để đánh dấu tiến độ.

**Goal:** Dựng trọn kế hoạch sản xuất cho cả 6 đơn hàng đang có trên DB `svn_erp_trong`, mỗi đơn
cố tình đi một nhánh nghiệp vụ khác nhau (kho đủ · kho thiếu phải mua · vật tư thay thế · routing
dựng tay có bước thuê ngoài · tranh giữ chỗ · bài ghép), **toàn bộ bằng thao tác chuột/bàn phím
thật trên dev-browser**.

**Architecture:** Đây là plan THAO TÁC DỮ LIỆU trên giao diện đang chạy, không sửa mã nguồn. Mỗi
task là một chuỗi thao tác UI có thể nghiệm thu độc lập bằng thứ nhìn thấy trên màn hình. Thứ tự
bắt buộc: khai đủ danh mục nền (công thức lượng của máy) → thu cọc → chốt đơn → chuyển xuống sản
xuất → tạo lệnh → dựng routing chi tiết hơn bài tính giá → khai vật tư → bài ghép → cân đối/giữ
chỗ/đề nghị mua → luồng mua → đánh dấu Sẵn sàng.

**Tech Stack:** FE React tại http://localhost:5173 · BE FastAPI 127.0.0.1:8000 trỏ Postgres
`svn_erp_trong` · điều khiển giao diện bằng Browser pane (`mcp__Claude_Browser__*`).

**Spec:** Không có file spec riêng. Yêu cầu gốc của chủ nằm trong hội thoại, trích nguyên văn ở
mục Global Constraints bên dưới.

## Global Constraints

- *"hiện tại đang có mấy đơn hàng đó, cho nó xuống kế hoạch hết đi, bây giờ bạn phải thao tác như
  nào cho xong full kế hoạch này"* — cả 6 đơn phải xuống kế hoạch, không bỏ đơn nào.
- *"nhớ là cả việc thêm công đoạn ở lsx cho nó mịn hơn đấy nhé đừng giữ nguyên routing công đoạn
  lúc in"* — routing của mỗi lệnh PHẢI nhiều bước hơn danh sách công đoạn của bài tính giá.
- *"tạm thời logic về tiền khi phát hành lệnh thì chưa bàn"* — dừng TRƯỚC nút phát hành lệnh;
  không bàn, không sửa gì về tiền lúc phát hành.
- *"tạm thời tự thêm thủ công ở dưới kế hoạch sản xuất đi"* — không xây tính năng tự sinh bước;
  chèn tay từng bước.
- Thuê ngoài = khai nhà thầu như một MÁY trong danh mục Thiết bị & Máy móc, tên kèm hậu tố
  `thuê ngoài – <tên nhà in>`, rồi ở kế hoạch chọn máy đó + đặt Loại bước = Thuê ngoài.
- CLAUDE.md: *"Code xong một luồng nghiệp vụ có UI → BẮT BUỘC thao tác lại ĐÚNG luồng đó bằng
  chuột/bàn phím thật trên dev-browser trước khi báo 'xong', KHÔNG dùng API/curl thay bất kỳ bước
  nào… Nếu vì lý do nào đó buộc phải tắt qua API ở một đoạn, phải tự nói rõ ngay lúc báo cáo."*
- CLAUDE.md: KHÔNG chạy `./init.ps1`. Không `python -c` trần trong `backend/`.
- Tối đa 5 dev-browser cùng lúc.
- Backend cổng 8000 phải trỏ `svn_erp_trong` (đã chuyển ở đầu phiên); nếu bị khởi động lại bằng
  `.env` mặc định nó sẽ quay về `svn_erp_local` — kiểm lại trước khi thao tác.
- Không commit, không push (chủ chưa yêu cầu).

## Số liệu nền đã đọc từ DB (dùng để đối chiếu khi thao tác)

Đơn hàng:

| Đơn | Hạng mục | SL | Trạng thái | Cọc 30% cần | Đã thu |
|---|---|---|---|---|---|
| DH001 | Thẻ nhân viên | 500 cái | Đã chốt | 178.740 | 0 |
| DH002 | Hộp bánh 200g | 10.000 con | Đã chốt | 6.519.763 | 0 |
| DH003 | Bìa sách + Ruột sách 192 trang | 2.000 + 2.000 | Đã chốt | 15.058.249 | 0 |
| DH004 | Bìa sách + Ruột sách 192 trang | 2.000 + 2.000 | **Nháp** | — | — |
| DH005 | Bìa sách + Ruột sách 192 trang | 2.000 + 2.000 | Đã chuyển SX, đã có LSX26-0003/0004 | — | — |
| DH006 | Bìa sách + Ruột sách 192 trang | 2.000 + 2.000 | **Nháp** | — | — |

Quy cách lấy từ phiếu tính giá:

| Hạng mục | Giấy | Khổ nguyên | Con/tờ | Tờ cần | Màu | Công đoạn bài tính giá |
|---|---|---|---|---|---|---|
| Thẻ nhân viên | C300 | 390×540 | 42 | 12 | 4/1 | In khổ nhỏ · Cán màng mờ · Bế · KCS thành phẩm |
| Hộp bánh 200g | C300 | 1090×790 | 4 | 2.500 | 4/0 | In khổ vừa · Cán màng mờ · Bế · Dán hộp · KCS thành phẩm |
| Bìa sách | C300 | 1090×790 | 9 | 223 | 4/0 | In khổ vừa · Cán màng mờ · Cắt thành phẩm |
| Ruột sách 192 trang | C150 | 650×980 | 16 | 12.000 (6 tờ/cuốn) | 1/1 | In khổ vừa · Gấp tay · Bắt tay · Vào bìa keo nhiệt · Xén 3 mặt · KCS thành phẩm |

Tồn kho giấy (Kho Giấy, đơn vị tính giá là **kg**): C100 500 · C150 800 · C200 700 · C250 600 ·
C300 500. Đơn giá/kg: C100 23.000 · C150 22.000 · C200 22.000 · C250 21.500 · C300 21.000.
Vật tư thay thế đã khai sẵn: C300 → [C250]; C150 → [C100, C200]; C250 → [C200, C300].

Nhu cầu giấy quy ra kg theo công thức danh mục `dinh_luong * dai_nguyen * rong_nguyen * to_nguyen`
(chưa cộng bù hao): thẻ 0,76 · hộp bánh 645,8 · mỗi bìa sách 57,6 · mỗi ruột sách 1.146,6. Tổng
C300 ≈ 877 kg / tồn 500 → thiếu. Tổng C150 ≈ 4.587 kg / tồn 800 → thiếu nặng. Con số chính xác
lấy từ bảng cân đối trên màn hình, bảng này chỉ để biết trước đâu sẽ đỏ.

Danh mục công đoạn dùng để chèn thêm: CD-0101 Bình bài & dàn trang (bài→bài) · CD-0102 Ghi kẽm CTP
(kẽm→kẽm) · CD-0103 In proof duyệt màu (bản proof) · CD-0104 Làm khuôn bế (bộ) · CD-0111 Xả giấy
(pha khổ) (tờ nguyên→tờ) · CD-0112 Cắt demi / chia tờ (tờ→tờ) · CD-0152 Bóc phế sau bế (con→con) ·
CD-0172 Đếm & bó thành phẩm (cái→cái) · CD-0181 Đóng thùng & dán nhãn (cái→cái).

Máy sẽ gán: CTP-01 CTP Screen 8600 (18 kẽm/giờ) · TI-01 Máy in proof 60cm (2 bản/giờ) · IN-02 Máy
4 màu Mitsubishi 79×109 (6.000 tờ/giờ) · IN-03 Máy 5 màu Mitsubishi 54×79 (9.000 tờ/giờ) · UV-03
Máy cán màng 1080 số 1 (500 m²/giờ) · BE-01 Bế tự động Yawa 1050 (4.500 nhịp/giờ) · DAN-01 Dán hộp
mềm máy nhỏ (10.000 hộp/giờ).

Tổ: Tổ kỹ thuật · Tổ in · Tổ cán phủ · Tổ bế · Tổ dán · Tổ cắt · Tổ thành phẩm / KCS · Tổ bồi ·
Tổ giao hàng.

---

### Task 1: Khai công thức lượng cho các máy sẽ dùng

**Vì sao đứng đầu:** máy chỉ đo bằng `tờ/giờ` mới tự bắc cầu ra thời lượng. CTP đo `kẽm/giờ`, proof
đo `bản proof/giờ`, cán màng đo `m²/giờ`, bế đo `nhịp/giờ`, dán đo `hộp/giờ` — cả năm loại này
`cong_thuc_luong` đang TRỐNG, mà danh mục Đơn vị chỉ có 5 cầu quy đổi (kg→g, m→mm, m²→cm², ram→tờ,
tấn→kg), không có cầu nào tới `nhịp`/`kẽm`/`hộp`/`bản proof`. Không khai thì các bước đó ra 0 phút
và Gantt không có gì để đặt.

**Màn hình:** Cấu hình danh mục → Thiết bị & Máy móc.

- [ ] **Bước 1: BE-01** — mở máy `BE-01 Bế tự động Yawa 1050`, điền ô **Công thức lượng** =
  `sl_vao`, lưu. Ý nghĩa: một tờ qua máy là một nhịp dập.
- [ ] **Bước 2: UV-03** — `Máy cán màng 1080 (số 1)`, Công thức lượng = `sl_vao * dai_in * rong_in`
  (ra m², khớp cách khai của đầu việc khoán KH-0004 Cán màng).
- [ ] **Bước 3: DAN-01** — `Dán hộp mềm máy nhỏ tự động (≤60cm)`, Công thức lượng = `sl_ra`
  (số hộp ra khỏi máy).
- [ ] **Bước 4: CTP-01** — `CTP Screen 8600 (Nhật)`, Công thức lượng = `so_kem`.
- [ ] **Bước 5: TI-01** — `Máy in proof – 60cm`, Công thức lượng = `so_mat`.
- [ ] **Bước 6: Nghiệm thu** — mở lại từng máy, xác nhận ô Công thức lượng giữ đúng chuỗi vừa gõ.

**Nghiệm thu task:** 5 máy trên đều hiện công thức; các máy còn lại (BE-02…BE-10, UV-01/04/05,
DAN-02…07, CTP-02, TI-02) vẫn trống — ghi nhận là nợ, không thuộc phạm vi plan này.

---

### Task 2: Đổi đầu việc khoán "Bế" sang đơn vị nhịp

**Vì sao:** chủ mô tả khoán bế là *"150 đ / nhịp"*. Danh mục đang khai KH-0006 Bế = 150 đ/**tờ**,
công thức `sl_vao`. Cùng số tiền khi một tờ dập một nhịp, nhưng sai ngay khi khuôn nhỏ hơn tờ phải
dập hai lượt. **Giả định đã chốt:** đổi sang `nhịp` và giữ đơn giá 150, công thức `sl_vao`; nếu
xưởng có khuôn dập 2 lượt thì sửa công thức thành `sl_vao * 2` ở chính bước lệnh sau.

**Màn hình:** Cấu hình danh mục → Công việc khoán.

- [ ] **Bước 1:** mở dòng `KH-0006 · Bế · Tổ bế`.
- [ ] **Bước 2:** đổi ô Đơn vị từ `tờ` sang `nhịp`; giữ Đơn giá 150; giữ Công thức lượng `sl_vao`.
- [ ] **Bước 3:** lưu, mở lại kiểm tra hiện `nhịp` và `150`.

**Nghiệm thu task:** dòng KH-0006 hiện `nhịp` · `150` · `sl_vao`.

---

### Task 3: Khai máy thuê ngoài trong danh mục

**Màn hình:** Cấu hình danh mục → Thiết bị & Máy móc → thêm mới.

- [ ] **Bước 1:** tạo máy mới với Mã `UV-NG-01`, Tên `Máy cán màng 1080 — thuê ngoài – Cơ sở Tân Phát`.
- [ ] **Bước 2:** Loại máy = `Cán màng / UV`. Tốc độ = `450`, Đơn vị tốc độ = `m²/giờ`, Công thức
  lượng = `sl_vao * dai_in * rong_in`, Thời gian chuẩn bị mặc định = `40` phút, Số nhân công = `2`.
  (Chậm hơn và chuẩn bị lâu hơn máy nhà UV-03 — đúng tính chất gửi hàng đi gia công.)
- [ ] **Bước 3:** lưu, xác nhận máy xuất hiện trong danh sách với đúng hậu tố tên.

**Nghiệm thu task:** danh mục có `UV-NG-01` tên chứa `thuê ngoài – Cơ sở Tân Phát`, tốc độ 450 m²/giờ.

---

### Task 4: Kế toán thu cọc cho DH001, DH002, DH003

**Vì sao:** cả ba đơn đặt cọc 30% và chưa thu đồng nào; màn Đơn hàng bán ghi rõ *"Chờ kế toán thu
đủ cọc (bước 'Cọc') — đủ cọc rồi mới bật nút 'Chuyển xuống sản xuất'"*. Không thu thì Task 6 tắc.

**Màn hình:** Kinh doanh → Đơn hàng bán → mở đơn → khối vòng đời, mục Cọc.

- [ ] **Bước 1:** mở DH001, ghi nhận cọc đã thu `178.740` (đúng bằng số cần), lưu.
- [ ] **Bước 2:** mở DH002, ghi nhận cọc `6.519.763`.
- [ ] **Bước 3:** mở DH003, ghi nhận cọc `15.058.249`.
- [ ] **Bước 4:** với mỗi đơn, xác nhận nút **Chuyển xuống sản xuất →** đã sáng lên.

**Nghiệm thu task:** ba đơn đều hết dòng cảnh báo thiếu cọc và nút chuyển xuống sản xuất bấm được.

---

### Task 5: Chốt DH004 và DH006

**Màn hình:** Kinh doanh → Đơn hàng bán.

- [ ] **Bước 1:** mở DH004 (đang Nháp), bấm **Chốt đơn**, xác nhận.
- [ ] **Bước 2:** mở DH006, bấm **Chốt đơn**, xác nhận.
- [ ] **Bước 3:** kiểm tra cả hai chuyển sang trạng thái đã chốt và không đòi cọc (hai đơn này
  không đặt cọc phần trăm nào).

**Nghiệm thu task:** danh sách đơn hàng hiện DH001–DH006 đều ở trạng thái đã chốt, không còn Nháp.

---

### Task 6: Chuyển 5 đơn còn lại xuống sản xuất

DH005 đã chuyển từ trước (`san_xuat_released_at` = 04/09/2026), không bấm lại.

**Màn hình:** Kinh doanh → Đơn hàng bán → từng đơn.

- [ ] **Bước 1:** DH001 → **Chuyển xuống sản xuất →**.
- [ ] **Bước 2:** DH002 → **Chuyển xuống sản xuất →**.
- [ ] **Bước 3:** DH003 → **Chuyển xuống sản xuất →**.
- [ ] **Bước 4:** DH004 → **Chuyển xuống sản xuất →**.
- [ ] **Bước 5:** DH006 → **Chuyển xuống sản xuất →**.
- [ ] **Bước 6:** mở Sản xuất → Kế hoạch sản xuất, tab **Hàng chờ tiếp nhận** phải đếm 5 đơn.

**Nghiệm thu task:** tab Hàng chờ tiếp nhận hiện đúng 5 dòng DH001, DH002, DH003, DH004, DH006.

---

### Task 7: Tạo lệnh sản xuất cho 5 đơn trong hàng chờ

Mỗi đơn sách sinh 2 lệnh (Bìa, Ruột); DH001 và DH002 mỗi đơn 1 lệnh. Tổng sau task: 2 lệnh cũ của
DH005 + 1 + 1 + 2 + 2 + 2 = **10 lệnh**.

**Màn hình:** Sản xuất → Kế hoạch sản xuất → tab Hàng chờ tiếp nhận.

- [ ] **Bước 1:** dòng DH001 → **Xem trước lệnh dự kiến**, đọc xem routing có kế thừa công đoạn của
  bài tính giá hay rỗng, rồi tạo lệnh.
- [ ] **Bước 2:** lặp cho DH002, DH003, DH004, DH006.
- [ ] **Bước 3:** sang tab **Lệnh sản xuất**, đếm đủ 10 lệnh và ghi lại mã lệnh của từng hạng mục
  để dùng ở các task sau.

**Nghiệm thu task:** tab Lệnh sản xuất liệt kê 10 lệnh, mỗi lệnh gắn đúng đơn và đúng tên hạng mục.

---

### Task 8: Routing DH001 — Thẻ nhân viên (ca trơn, kho đủ)

Bài tính giá có 4 công đoạn. Routing lệnh phải thành **9 bước**.

**Màn hình:** Kế hoạch sản xuất → tab Lệnh sản xuất → mở lệnh của DH001 → bảng routing.

Routing đích, theo thứ tự:

| # | Công đoạn | Loại bước | Tổ | Máy | Đầu việc khoán |
|---|---|---|---|---|---|
| 1 | Bình bài & dàn trang | Tổ | Tổ kỹ thuật | — | KH-0015 Bình bài & dàn trang |
| 2 | Ghi kẽm CTP | Máy | Tổ kỹ thuật | CTP-01 | KH-0013 Bình bài & ra kẽm |
| 3 | In proof duyệt màu | Máy | Tổ kỹ thuật | TI-01 | KH-0016 In proof duyệt màu |
| 4 | In AB- Máy in-11 x 11-khổ nhỏ | Máy | Tổ in | IN-03 | KH-0002 In offset |
| 5 | cán màng mờ - cán màng 11 x 11 | Máy | Tổ cán phủ | UV-03 | KH-0004 Cán màng |
| 6 | Bế | Máy | Tổ bế | BE-01 | KH-0006 Bế |
| 7 | Bóc phế sau bế | Tổ | Tổ bế | — | KH-0007 Bóc phế sau bế |
| 8 | KCS thành phẩm | Tổ | Tổ thành phẩm / KCS | — | — |
| 9 | Đếm & bó thành phẩm | Tổ | Tổ thành phẩm / KCS | — | KH-0028 Đếm & bó thành phẩm |

- [ ] **Bước 1:** chèn 3 bước trước In bằng nút **Thêm công đoạn** ở dòng tương ứng (nút chèn SAU
  một bước cụ thể, không có nút thêm chung).
- [ ] **Bước 2:** chèn Bóc phế sau bế ngay sau Bế, và Đếm & bó thành phẩm sau KCS.
- [ ] **Bước 3:** mở drawer từng bước, tab **Phân công & Thiết bị**: đặt Tổ phụ trách và Máy sản
  xuất theo bảng trên.
- [ ] **Bước 4:** vẫn ở drawer, khối **Đầu việc khoán lương thợ**: chọn đầu việc theo bảng.
- [ ] **Bước 5:** bấm **Lưu công đoạn**.
- [ ] **Bước 6:** mở lại lệnh, kiểm tra bước Bế hiện thời gian chiếm máy khác 0 (bằng chứng công
  thức lượng ở Task 1 có tác dụng) và bảng routing đủ 9 dòng.

**Nghiệm thu task:** routing 9 bước, mọi bước có tổ, bước máy có máy, bước Bế có số phút chiếm máy.

---

### Task 9: Khai vật tư cho lệnh DH001

Bảng cân đối chỉ nhìn thấy vật tư khai ở BƯỚC, nên không khai thì Task 15 rỗng.

**Màn hình:** drawer bước → tab **Vật tư** (Định mức vật tư tiêu hao — BOM).

- [ ] **Bước 1:** bước In — thêm giấy `C300`; thêm 4 mực `VT-MUC-K/C/M/Y`; thêm `VT-DM-01 Dung môi
  rửa máy in`.
- [ ] **Bước 2:** bước Cán màng mờ — thêm `VT-MANG-BOPP Màng BOPP cán bóng`.
- [ ] **Bước 3:** bước Đếm & bó thành phẩm — thêm `VT-BANGKEO-01 Băng keo trong 48mm`.
- [ ] **Bước 4:** Lưu công đoạn, kiểm tra badge số vật tư trên tab Vật tư của từng bước khớp số
  dòng vừa thêm.

**Nghiệm thu task:** ba bước trên có badge vật tư > 0; các món đều tự tính ra lượng (không báo
thiếu biến).

---

### Task 10: Routing + vật tư DH002 — Hộp bánh 200g (ca kho thiếu)

Bài tính giá 5 công đoạn → routing lệnh **11 bước**.

| # | Công đoạn | Loại bước | Tổ | Máy | Đầu việc khoán |
|---|---|---|---|---|---|
| 1 | Bình bài & dàn trang | Tổ | Tổ kỹ thuật | — | KH-0015 |
| 2 | Làm khuôn bế | Tổ | Tổ kỹ thuật | — | KH-0017 Làm khuôn bế |
| 3 | Ghi kẽm CTP | Máy | Tổ kỹ thuật | CTP-01 | KH-0013 |
| 4 | In proof duyệt màu | Máy | Tổ kỹ thuật | TI-01 | KH-0016 |
| 5 | In AB- Máy in-22 x 22-khổ vừa | Máy | Tổ in | IN-02 | KH-0002 |
| 6 | cán màng mờ - cán màng 11 x 11 | Máy | Tổ cán phủ | UV-03 | KH-0004 |
| 7 | Bế | Máy | Tổ bế | BE-01 | KH-0006 |
| 8 | Bóc phế sau bế | Tổ | Tổ bế | — | KH-0007 |
| 9 | Dán hộp | Máy | Tổ dán | DAN-01 | KH-0008 Dán hộp |
| 10 | KCS thành phẩm | Tổ | Tổ thành phẩm / KCS | — | — |
| 11 | Đóng thùng & dán nhãn | Tổ | Tổ giao hàng | — | KH-0014 Đóng gói & bó hàng |

- [ ] **Bước 1:** chèn 4 bước trước In (Bình bài, Làm khuôn bế, Ghi kẽm CTP, In proof).
- [ ] **Bước 2:** chèn Bóc phế sau bế sau Bế; chèn Đóng thùng & dán nhãn sau KCS.
- [ ] **Bước 3:** gán tổ/máy/đầu việc theo bảng, Lưu công đoạn.
- [ ] **Bước 4:** khai vật tư: bước In → `C300` + 4 mực + dung môi; Cán màng → `VT-MANG-BOPP`;
  Dán hộp → `VT-KEO-01 Keo dán hộp`; Đóng thùng → `VT-THUNG-01` + `VT-BANGKEO-01` + `VT-DAY-01`.
- [ ] **Bước 5:** kiểm tra bước Dán hộp có phút chiếm máy khác 0 (công thức `sl_ra` của DAN-01).

**Nghiệm thu task:** routing 11 bước; bước Bế và Dán hộp đều ra thời lượng; 4 bước có vật tư.

---

### Task 11: Routing + vật tư DH003 — Sách (ca vật tư thay thế)

Hai lệnh. Bìa 3 công đoạn → **6 bước**; Ruột 6 công đoạn → **10 bước**.

Lệnh **Bìa sách**:

| # | Công đoạn | Loại | Tổ | Máy | Đầu việc |
|---|---|---|---|---|---|
| 1 | Bình bài & dàn trang | Tổ | Tổ kỹ thuật | — | KH-0015 |
| 2 | Ghi kẽm CTP | Máy | Tổ kỹ thuật | CTP-01 | KH-0013 |
| 3 | In proof duyệt màu | Máy | Tổ kỹ thuật | TI-01 | KH-0016 |
| 4 | In AB- Máy in-22 x 22-khổ vừa | Máy | Tổ in | IN-02 | KH-0002 |
| 5 | cán màng mờ - cán màng 11 x 11 | Máy | Tổ cán phủ | UV-03 | KH-0004 |
| 6 | Cắt thành phẩm | Máy | Tổ cắt | — | KH-0030 Cắt thành phẩm |

Lệnh **Ruột sách 192 trang**:

| # | Công đoạn | Loại | Tổ | Máy | Đầu việc |
|---|---|---|---|---|---|
| 1 | Bình bài & dàn trang | Tổ | Tổ kỹ thuật | — | KH-0015 |
| 2 | Ghi kẽm CTP | Máy | Tổ kỹ thuật | CTP-01 | KH-0013 |
| 3 | In AB- Máy in-22 x 22-khổ vừa | Máy | Tổ in | IN-02 | KH-0002 |
| 4 | Cắt demi / chia tờ | Tổ | Tổ cắt | — | KH-0019 Cắt demi / chia tờ |
| 5 | Gấp tay | Tổ | Tổ thành phẩm / KCS | — | KH-0009 Gấp tay |
| 6 | Bắt tay | Tổ | Tổ thành phẩm / KCS | — | KH-0010 Bắt tay |
| 7 | Vào bìa keo nhiệt | Tổ | Tổ thành phẩm / KCS | — | KH-0011 Vào bìa keo nhiệt |
| 8 | Xén 3 mặt | Tổ | Tổ cắt | — | KH-0012 Xén 3 mặt |
| 9 | KCS thành phẩm | Tổ | Tổ thành phẩm / KCS | — | — |
| 10 | Đếm & bó thành phẩm | Tổ | Tổ thành phẩm / KCS | — | KH-0028 |

- [ ] **Bước 1:** dựng routing lệnh Bìa theo bảng, Lưu công đoạn.
- [ ] **Bước 2:** dựng routing lệnh Ruột theo bảng, Lưu công đoạn.
- [ ] **Bước 3:** khai vật tư lệnh Bìa: In → **`C250`** (không phải C300 — đây là nhánh vật tư thay
  thế, C250 đã khai là thay thế hợp lệ của C300 và còn tồn 600 kg) + 4 mực + dung môi; Cán màng →
  `VT-MANG-BOPP`.
- [ ] **Bước 4:** khai vật tư lệnh Ruột: In → `C150` + `VT-MUC-K` + dung môi; Vào bìa keo nhiệt →
  `VT-KEO-01`; Đếm & bó → `VT-BANGKEO-01`.
- [ ] **Bước 5:** kiểm tra ô chọn giấy ở bước In của lệnh Bìa có gợi ý/chấp nhận C250 như hàng thay
  thế và lượng tính ra ≈ 57,6 kg.

**Nghiệm thu task:** hai lệnh có 6 và 10 bước; lệnh Bìa dùng C250 chứ không phải C300.

---

### Task 12: Routing + vật tư DH005 — Sách, có bước thuê ngoài

Hai lệnh LSX26-0003 (Bìa) và LSX26-0004 (Ruột) đã tồn tại, đang Nháp, routing rỗng, đang báo thiếu
giấy/khổ/routing. Dựng từ đầu.

- [ ] **Bước 1:** lệnh Bìa — dựng đủ 6 bước như bảng Bìa ở Task 11.
- [ ] **Bước 2:** riêng bước 5 **cán màng mờ**, tại tab Phân công & Thiết bị đặt **Loại bước thực
  hiện = Thuê ngoài**, Tổ phụ trách = Tổ cán phủ, Máy sản xuất = `UV-NG-01 Máy cán màng 1080 — thuê
  ngoài – Cơ sở Tân Phát`.
- [ ] **Bước 3:** xác nhận bước thuê ngoài nhập liệu y hệt bước máy (vẫn có máy, vẫn có số người
  theo kíp máy) và **không** hiện tiền khoán — đây là điểm khác duy nhất so với bước máy.
- [ ] **Bước 4:** lệnh Ruột — dựng đủ 10 bước như bảng Ruột ở Task 11.
- [ ] **Bước 5:** khai vật tư: Bìa → `C300` + 4 mực + dung môi + màng BOPP; Ruột → `C150` +
  `VT-MUC-K` + dung môi + keo + băng keo.
- [ ] **Bước 6:** Lưu công đoạn cả hai lệnh; kiểm tra khối "Vướng" của lệnh không còn `thiếu
  routing`.

**Nghiệm thu task:** LSX26-0003 có 6 bước trong đó bước cán màng là Thuê ngoài gắn máy UV-NG-01 và
không sinh tiền khoán; LSX26-0004 có 10 bước.

---

### Task 13: Routing + vật tư DH004 — Sách (ca tranh giữ chỗ)

Cùng khuôn routing với DH003 nhưng **dùng đúng C300** cho bìa, để cố tình tranh cùng lô giấy với
DH005 và DH006 ở Task 15.

- [ ] **Bước 1:** lệnh Bìa — dựng 6 bước theo bảng Bìa ở Task 11.
- [ ] **Bước 2:** lệnh Ruột — dựng 10 bước theo bảng Ruột ở Task 11.
- [ ] **Bước 3:** khai vật tư Bìa: In → `C300` + 4 mực + dung môi; Cán màng → `VT-MANG-BOPP`.
- [ ] **Bước 4:** khai vật tư Ruột: In → `C150` + `VT-MUC-K` + dung môi; Vào bìa keo nhiệt →
  `VT-KEO-01`; Đếm & bó → `VT-BANGKEO-01`.
- [ ] **Bước 5:** Lưu công đoạn cả hai lệnh.

**Nghiệm thu task:** hai lệnh đủ bước, bìa dùng C300.

---

### Task 14: Routing + vật tư DH006 — Sách (ca bài ghép)

Giống DH004 (bìa dùng C300) để hai bìa cùng khổ 1090×790, cùng giấy, ghép chung được tờ in.

- [ ] **Bước 1:** lệnh Bìa — dựng 6 bước theo bảng Bìa ở Task 11, vật tư In dùng `C300`.
- [ ] **Bước 2:** lệnh Ruột — dựng 10 bước theo bảng Ruột ở Task 11, vật tư In dùng `C150`.
- [ ] **Bước 3:** Lưu công đoạn cả hai lệnh.
- [ ] **Bước 4:** mở Sản xuất → Bài ghép, tạo bài ghép mới gộp bước **In** của lệnh Bìa DH006 với
  bước **In** của lệnh Bìa DH004 (cùng giấy C300, cùng khổ 1090×790, cùng 4 màu 1 mặt).
- [ ] **Bước 5:** xem sơ đồ bài ghép, xác nhận tổng số tờ in chung nhỏ hơn tổng hai lệnh chạy riêng.
- [ ] **Bước 6:** quay lại Kế hoạch sản xuất, xác nhận hai lệnh Bìa hiện băng nhãn bài ghép.

**Nghiệm thu task:** một bài ghép chứa 2 thành viên là bước In của bìa DH004 và bìa DH006, có sơ đồ.

---

### Task 15: Cân đối vật tư và giữ chỗ

**Màn hình:** Sản xuất → Kế hoạch vật tư, cả hai tab **Theo mặt hàng** và **Theo lệnh sản xuất**.

- [ ] **Bước 1:** đọc tab Theo mặt hàng, ghi lại từng dòng: tồn, nhu cầu, thiếu. Đối chiếu với dự
  đoán ở đầu plan (C300 thiếu, C150 thiếu nặng, C250 đủ cho bìa DH003).
- [ ] **Bước 2:** tab Theo lệnh sản xuất → bật **Giữ chỗ** cho lệnh DH001 (nhu cầu 0,76 kg C300,
  chắc chắn đủ) — đây là ca trơn.
- [ ] **Bước 3:** bật Giữ chỗ cho lệnh Bìa DH003 (C250).
- [ ] **Bước 4:** bật Giữ chỗ cho lệnh Bìa DH004, rồi thử bật tiếp cho Bìa DH005 và Bìa DH006 —
  quan sát và ghi lại hệ thống xử lý tranh chấp thế nào khi tổng giữ chỗ vượt tồn C300.
- [ ] **Bước 5:** với các dòng thiếu, ghi lại con số thiếu chính xác để dùng ở Task 16.

**Nghiệm thu task:** có ít nhất 1 lệnh giữ chỗ thành công và 1 lệnh bị chặn/cảnh báo vì hết tồn;
bảng cân đối liệt kê rõ các dòng thiếu.

---

### Task 16: Đề nghị mua cho phần thiếu và chạy trọn luồng mua

- [ ] **Bước 1:** ở màn Kế hoạch vật tư, bấm **Đề nghị mua** trên dòng `C300` thiếu; xem trước rồi
  tạo.
- [ ] **Bước 2:** bấm **Đề nghị mua** trên dòng `C150` thiếu.
- [ ] **Bước 3:** sang Thu mua → Yêu cầu mua hàng, mở phiếu vừa sinh, kiểm tra nó dẫn chiếu đúng
  lệnh nguồn, rồi trình duyệt và duyệt.
- [ ] **Bước 4:** Thu mua → Mua hàng, tạo đơn mua hàng từ yêu cầu đã duyệt, chọn nhà cung cấp, chốt.
- [ ] **Bước 5:** Kho hàng → Yêu cầu nhập xuất, làm phiếu nhập kho cho lô giấy về, ghi sổ.
- [ ] **Bước 6:** quay lại Kế hoạch vật tư, xác nhận tồn C300/C150 đã tăng và dòng thiếu chuyển
  sang đủ.
- [ ] **Bước 7:** bật lại Giữ chỗ cho các lệnh trước đó bị chặn.

**Nghiệm thu task:** tồn kho tăng đúng lượng vừa nhập; các lệnh còn lại giữ chỗ được; bảng cân đối
không còn dòng đỏ.

---

### Task 17: Đánh dấu Sẵn sàng và tổng kết

- [ ] **Bước 1:** mở lần lượt 10 lệnh, kiểm tra khối **Vướng** trống (không thiếu giấy, khổ,
  routing, tổ/máy).
- [ ] **Bước 2:** chuyển trạng thái từng lệnh sang **Sẵn sàng**.
- [ ] **Bước 3:** tab Lệnh sản xuất, lọc trạng thái Sẵn sàng, xác nhận đủ 10 lệnh.
- [ ] **Bước 4:** **DỪNG** — không bấm phát hành lệnh, vì logic tiền lúc phát hành đang được gác
  theo yêu cầu của chủ.
- [ ] **Bước 5:** viết báo cáo nghiệm thu liệt kê cụ thể từng bước đã bấm gì/gõ gì/thấy gì, nêu rõ
  mọi đoạn (nếu có) buộc phải đi tắt qua API.

**Nghiệm thu task:** 10 lệnh ở trạng thái Sẵn sàng, không lệnh nào được phát hành.

---

## Self-review

**Phủ yêu cầu:** cả 6 đơn xuống kế hoạch (Task 5–7) ✓ · routing mịn hơn bài tính giá ở mọi lệnh,
4→9, 5→11, 3→6, 6→10 (Task 8, 10–14) ✓ · thêm bước thủ công không xây tính năng ✓ · vật tư thay thế
(Task 11) ✓ · kho hết → mua (Task 16) ✓ · giữ chỗ và tranh giữ chỗ (Task 15) ✓ · thuê ngoài theo
cơ chế máy-có-hậu-tố (Task 3 + 12) ✓ · bài ghép (Task 14) ✓ · dừng trước phát hành ✓.

**Rủi ro đã biết:** (a) routing kế thừa từ bài tính giá có thể rỗng như hai lệnh DH005 hiện tại —
plan vẫn chạy được vì Task 8/10–14 nêu routing ĐÍCH đầy đủ, chèn thêm hay dựng từ đầu đều ra cùng
kết quả; (b) tồn C150 thiếu tới ~3.800 kg nên gần như mọi lệnh ruột sách đều phải chờ mua — chấp
nhận, đó chính là nhánh nghiệp vụ cần diễn; (c) đơn vị tồn kho giấy giả định là kg, phải xác nhận
lại trên màn Kho ở Task 15 trước khi kết luận thiếu/đủ.

---

## NHẬT KÝ THỰC THI (UI thật, dev-browser tab "seed")

- **Task 1 — XONG (05/09/2026).** Khai `cong_thuc_luong` cho 5 máy tại Cấu hình danh mục → Thiết bị & Máy móc → mở máy → tab "Cách đo lượng" → bấm nút biến ở "DANH SÁCH BIẾN KHẢ DỤNG" (KHÔNG gõ tay — gõ tay bị autocomplete chọn nhầm biến) → "Lưu thay đổi".
  - BE-01 Bế tự động Yawa 1050 → chip `SL vào của công đoạn` (`sl_vao`)
  - UV-03 Máy cán màng 1080 (số 1) → `SL vào của công đoạn` × `Dài tờ in` × `Rộng tờ in`
  - DAN-01 Dán hộp mềm máy nhỏ tự động (≤60cm) → `SL ra của công đoạn` (`sl_ra`)
  - CTP-01 CTP Screen 8600 (Nhật) → `Số bản kẽm` (`so_kem`)
  - TI-01 Máy in proof – 60cm → `Số mặt` (`so_mat`)
  - Đã mở lại đủ 5 máy sau khi lưu, tab "Cách đo lượng" hiển thị đúng chip ⇒ đã ghi DB.
  - Ghi chú thao tác: dialog có animation vào; khung hình chỉ tiến khi có screenshot, nên phải chụp 1-2 lần sau khi mở rồi mới bấm tab, không thì click rơi ra ngoài và đóng dialog.
- **Task 2 — XONG.** Cấu hình danh mục → Công việc khoán → mở `KH-0006 Bế`:
  - Ô "Đơn vị tính khoán": xoá `tờ`, gõ `nhip` trong ô tìm, chọn gợi ý `nhịp` (mã `nhip` có sẵn trong danh mục Đơn vị).
  - Đơn giá giữ `150` đ (đã đúng từ trước).
  - Ghi chú sửa thành "Khoán theo NHỊP máy bế: 150 đ/nhịp. Cách đo lượng = sl_vao (1 tờ vào = 1 nhịp)."
  - Tab "Cách đo lượng" của đầu việc: đã sẵn chip `SL vào của công đoạn` — giữ nguyên.
  - Sau "Lưu thay đổi", dòng KH-0006 trong bảng hiện ĐƠN VỊ = `nhịp`, ĐƠN GIÁ = 150 đ.
- **Task 3 — XONG.** Thiết bị & Máy móc → "Thêm thiết bị & máy móc":
  - Thông tin chung: Mã `UV-NG-01`, Tên `Máy cán màng 1080 — thuê ngoài – Cơ sở Tân Phát`,
    Nhóm máy `Cán màng / UV`, Hãng sản xuất `Cơ sở Tân Phát (gia công ngoài)`, Model `1080`.
  - Thông số kỹ thuật: Tốc độ trung bình `450`, Đơn vị tốc độ `m²/h`, Số người vận hành `2`,
    Thời gian chuẩn bị = "Điền tổng — gõ thẳng một số" → `40` phút; ghi chú nói rõ đây là máy thuê ngoài,
    bước chạy trên máy này không tính tiền khoán và không ghi sản lượng cho tổ.
  - Cách đo lượng: `SL vào của công đoạn × Dài tờ in × Rộng tờ in`.
  - Bẫy đã gặp: hàng CHÈN TOÁN TỬ có `+ − × ÷` sát nhau — bấm nhầm `÷`; xoá bằng cách click vào ô nhập
    trống bên phải rồi nhấn `Backspace` (KHÔNG phải "BackSpace").
  - Sau "Tạo mới": danh sách 42 → 43 mục, nhóm Cán màng / UV 5 → 6, dòng UV-NG-01 hiện
    `450 m²/h · Chuẩn bị: 40 phút · 2 người · Xếp được`.
- **Task 4 — XONG (gộp luôn phần Task 6 của 3 đơn này).** Kinh doanh → Đơn hàng bán → mở đơn →
  cuộn xuống khối "Vòng đời đơn" → "Cọc & thu tiền" → nút **+ Lập phiếu thu cọc**:
  - Hình thức thu `Tiền mặt` (mặc định), Số tiền thực thu để nguyên số hệ điền sẵn, Ngày thu `05/09/2026`,
    Ghi chú "Thu cọc 30% theo hợp đồng - tiền mặt" → **Lập phiếu thu**.
  - DH001 `178.740đ` · DH002 `6.519.763đ` · DH003 `15.058.249đ` — mỗi lần đều hiện toast
    "Đơn DHxxx đã đủ cọc — chuyển xuống sản xuất được rồi", chấm "Cọc" chuyển xanh + chữ "đủ".
  - Bấm luôn **Chuyển xuống sản xuất →** cho cả 3 ⇒ toast "vừa chuyển xuống sản xuất",
    khối Sản xuất hiện `chờ kế hoạch`, Chuyển lúc `5/9/2026`, có link "Mở bàn Kế hoạch sản xuất".
  - Bẫy: ô "Ngày thu" là `input[type=date]` — hành động `type` KHÔNG vào; phải click vào ô rồi
    gửi từng phím số: `key "0 5 0 9 2 0 2 6"`.
- **Task 5 — XONG MỘT NỬA. DH006 chốt được, DH004 KHÔNG chốt được (dữ liệu hỏng, không phải lỗi thao tác).**
  - DH006: bấm **Sửa** → điền `Số PO khách = PO-SM-2026-006`, `Ngày giao cam kết = 30/09/2026`,
    `Lưu ý sản xuất` = "Bìa sách in ghép chung tay với bìa của đơn cùng loại (cùng C300, cùng khổ
    1090x790) - xem màn Bài ghép" → **Lưu** → **Chốt đơn** ⇒ ĐÃ CHỐT, ngày chốt 5/9/2026,
    mục Cọc ghi "không cần cọc" → **Chuyển xuống sản xuất →** ⇒ chờ kế hoạch.
  - DH004: bấm **Chốt đơn** báo lỗi đỏ *"Dòng \"Bìa sách\" trỏ tới sản phẩm tính giá đã bị xoá —
    không thể chốt đơn"*. Nguyên nhân (đã truy): `order_service.py:684-693` chặn chốt khi dòng đơn có
    `phieu_thanh_phan_id` nhưng bản ghi nguồn đã mất. Hai dòng của DH004 ghim `27` và `28`; các
    `PhieuThanhPhan` còn sống chỉ là `2, 24, 39, 40, 41`. PTG-2026-0004 (nguồn của BG26-0004) nay
    chứa thành phần "Thẻ nhân viên" (id 24) — tức phiếu đã bị sửa/ghi đè, thành phần cũ bị xoá và
    đơn DH004 mồ côi. Tab Thương mại của đơn KHOÁ theo báo giá nên UI không có đường sửa lại dòng.
    ⇒ **Bỏ DH004 khỏi kịch bản**, giữ nguyên trạng thái Nháp (không huỷ, không đụng DB).
  - Hệ quả: kịch bản chạy trên 5 đơn DH001 · DH002 · DH003 · DH005 · DH006. Nhánh "bài ghép" chuyển
    sang ghép bìa DH006 với bìa DH003 (cùng sách 192 trang, cùng C300, cùng khổ).
- **Task 6 + 7 — XONG (theo 5 đơn).** Sản xuất → Kế hoạch sản xuất:
  - Tab "Hàng chờ tiếp nhận" nhận đúng 4 đơn vừa chuyển (DH001, DH002, DH003, DH006); DH005 đã
    chuyển từ 04/09 nên không nằm ở hàng chờ.
  - Mỗi dòng bấm **Xem lệnh dự kiến** rồi **Xác nhận tạo N lệnh sản xuất**:
    - DH001 → `LSX26-0005` Thẻ nhân viên 500 cái — preview ghi "chưa có công đoạn" + cảnh báo đỏ
      "Chưa có bài tính giá" ⇒ routing phải dựng tay.
    - DH002 → `LSX26-0006` Hộp bánh 200g 10.000 cái — cũng "chưa có công đoạn".
    - DH003 → `LSX26-0007` Bìa sách + `LSX26-0008` Ruột sách 192 trang, 2.000 cái mỗi lệnh.
    - DH006 → `LSX26-0009` Bìa sách + `LSX26-0010` Ruột sách — preview đơn này CÓ bài tính giá
      (PTG-2026-0003) nên kế thừa bù hao/vào máy/giấy nguyên/bình bài/kẽm và công đoạn
      "In AB - Máy in-22 x 22-khổ nhỏ"; kèm 3 cảnh báo: hai thành phần chưa có công đoạn CHẾ BẢN/KẼM
      (chưa tính tiền kẽm) và công đoạn "KCS thành phẩm" chưa khai công thức tính giá (tính 0đ).
  - Tab "Lệnh sản xuất" đếm **8 lệnh** (không phải 10 như plan, vì DH004 bị loại): 0003+0004 (DH005),
    0005 (DH001), 0006 (DH002), 0007+0008 (DH003), 0009+0010 (DH006).
    LSX26-0009 hiện "3 bước · Tổ in", LSX26-0010 "6 bước · Tổ in"; sáu lệnh còn lại "Chưa có CĐ".
- **Task 8 — XONG (05/09/2026). LSX26-0005 / DH001 "Thẻ nhân viên" 500 cái — dựng routing tay 10 bước
  (plan viết 9; thêm "Xả giấy (pha khổ)" theo yêu cầu "cho nó mịn hơn, đừng giữ nguyên routing lúc in").**
  - Tab **Quy cách**: Giấy `C300` 300gsm · khổ nguyên `860×650` · khổ in `430×325` · thành phẩm `86×54` ·
    in 2 mặt (AB) · bleed `3` · khe cắt `3` · CMYK cả hai mặt ⇒ hệ tự ra **Số mảnh xả 4 · Số kẽm 8 ·
    Bình bài 20 con/tờ · Số bài in 1 · Cách bình "Máy tự bình"**. Chính vì 1 tờ nguyên cắt ra 4 tờ in mà
    bước Xả giấy là bắt buộc về mặt vật lý — đó là căn cứ thêm bước, không phải thêm cho đủ số.
  - Tab **Công đoạn** → view "Bảng danh sách". Routing rỗng nên lần đầu dùng nút empty-state
    **"+ Thêm công đoạn"**; từ dòng thứ hai trở đi CHỈ thêm được bằng **"Chèn công đoạn mới sau bước N"**
    trên chính dòng đó. Mỗi bước: mở drawer → tab "Cấu hình & Số lượng" chọn công đoạn + loại bước →
    tab "Phân công & Thiết bị" chọn máy / "Tổ lao động làm tay" → tab "Phụ thuộc" tick tiền nhiệm.
  - 10 bước đã lưu (bấm **"Lưu công đoạn"** ở bảng chính — sửa trong drawer chỉ nằm trong bộ nhớ):

    | # | Công đoạn | Loại | Tổ · Máy | Vào → Ra | Thời lượng | Tiền nhiệm |
    |---|---|---|---|---|---|---|
    | 10 | Bình bài & dàn trang | Tổ | Tổ kỹ thuật | bài in → bài in | — | Gốc |
    | 20 | Ghi kẽm CTP | Máy | Tổ kỹ thuật · CTP Screen 8600 (Nhật) | bản kẽm → bản kẽm | 27 phút | Bình bài |
    | 30 | In proof duyệt màu | Máy | Tổ kỹ thuật · Máy in proof – 60cm | bản proof → bản proof | 1 giờ | Bình bài |
    | 40 | Xả giấy (pha khổ) | Máy | Tổ cắt · Máy cắt tờ ITO 100 | 132 → 325 (1 tờ nguyên = 4 tờ) | 31 phút | Gốc |
    | 50 | In AB- Máy in-11 x 11-khổ nhỏ | Máy | Tổ in · Máy 5 màu Mitsubishi 54×79 | 325 tờ → 125 tờ | 1 giờ 19 phút | Ghi kẽm · In proof · Xả giấy |
    | 60 | cán màng mờ - cán màng 11 x 11 | Máy | Tổ cán phủ · Máy cán màng 1080 (số 1) | 125 tờ → 75 tờ | 2 phút | In AB |
    | 70 | Bế | Máy | Tổ bế · Bế tự động Yawa 1050 | 75 tờ → 500 con (1 tờ = 20 con) | **46 phút** | cán màng |
    | 80 | Bóc phế sau bế | Tổ | Tổ bế | 500 con → 500 con | 17 phút | Bế |
    | 90 | KCS thành phẩm | Tổ | Tổ thành phẩm / KCS | 500 cái → 500 cái | — | Bóc phế |
    | 100 | Đếm & bó thành phẩm | Tổ | Tổ thành phẩm / KCS | 500 cái → 500 cái | 15 phút | KCS |

  - **Nghiệm thu đạt**: bước Bế hiện **46 phút chiếm máy** (khác 0 ⇒ công thức lượng khai ở Task 1 có tác
    dụng thật); bảng đủ 10 dòng; mọi bước có tổ, mọi bước Máy có máy cụ thể.
    Header lệnh: SL ĐẶT 500 cái · VÀO MÁY 325 tờ · GIẤY NGUYÊN 132 tờ nguyên · BÌNH BÀI 20 con ·
    CÔNG ĐOẠN 10 · VẬT TƯ 7 món · HẠN GIAO 17/9/2026 · CÔNG THỢ 272.587 đ.
    Tổng thời gian dẫn **4 giờ 37 phút**.
  - **Sửa danh mục phát sinh trong lúc dựng (đều làm bằng UI, đều cần thật):**
    - `CD-0111 Xả giấy (pha khổ)` — ô "Máy làm được công đoạn này" mới chỉ tick nhóm `cắt`, mà nhóm `cắt`
      không có máy nào (bộ lọc trên màn Máy đếm `cắt 0`) ⇒ dropdown máy của bước rỗng. Tick thêm
      `Trước in` → "Lưu thay đổi" ⇒ 9 máy trước in hiện ra.
    - `TI-07 Máy cắt tờ ITO 100` — tab "Thông số kỹ thuật" khai `1 tấn/h`, mà đầu vào bước đo bằng
      *tờ nguyên* nên engine báo *"Chưa quy đổi được số lượng vào sang đơn vị của tốc độ"* và thời lượng
      hiện "—". Đổi thành **500 tờ nguyên/h** (= khoán trung bình 2.000 tờ/h của KH-0001 chia 4 tờ trên
      một tờ nguyên) + **Thời gian chuẩn bị "Điền tổng" = 15 phút**, ghi chú ghi rõ lý do đổi đơn vị.
      Sau khi lưu, mở lại lệnh: bước Xả giấy hiện **31 phút** (132 ÷ 500 = 15,8 phút chạy + 15 phút canh dao)
      và tổng thời gian dẫn nhảy 4 giờ 06 → **4 giờ 37 phút**.
  - **Bẫy thao tác dev-browser (ghi lại để các task sau khỏi vấp):**
    - Khung ảnh screenshot là 800×450, còn toạ độ mà `read_page`/`find` trả về là của viewport 1280×720 —
      quy đổi `viewport = frame × 1,6`.
    - Hai mũi tên **"Bước sau" / "Bước trước"** trong drawer DỊCH NGANG theo độ dài tên bước ⇒ tuyệt đối
      không bấm bằng toạ độ cứng, phải `find "Bước sau"` lấy ref. Bấm nhầm một lần đã tick oan 3 chip
      phụ thuộc ở bước "In proof duyệt màu"; đã bấm lại đúng 3 chip đó để bỏ tick và kiểm lại bằng JS
      (`[true,false,false,false,false,false,false,false,false]`).
    - Combobox chọn công đoạn trong drawer ĐỔI ref mỗi lần mở/chuyển bước ⇒ phải `find "chọn công đoạn"`
      lại trước từng lần đặt giá trị, không thì "ref not found or stale".
    - "Tổ phụ trách" trong drawer là READ-ONLY ("Khai ở danh mục Công đoạn — đổi tổ tại đó").
    - "Đầu việc khoán lương thợ" nằm ở tab *Phân công & Thiết bị* (bước Máy), không ở tab Cấu hình.
  - **Khuyết còn lại của lệnh này — nguyên nhân đã truy ra, KHÔNG tự vá (chờ lệnh):**
    `GET /api/lsx/{id}/mac-dinh-buoc/{cong_doan_id}` **500 với mọi công đoạn**. Gốc: schema
    `BuocMacDinhOut` bắt buộc `loai_buoc`, còn `LsxService.mac_dinh_buoc`
    (`backend/app/services/lsx_service.py:1674-1706`) CỐ TÌNH không trả field đó (docstring nói loại bước
    thuộc về chính bước KHSX, endpoint này không được ghi đè) ⇒ `lsx.py:514` ném ValidationError.
    Hệ quả thấy tận mắt: (1) `lsx_cong_doan.ten` lưu là "Công đoạn" cho MỌI bước, nên chip phụ thuộc
    trong drawer đều đọc là "Công đoạn" — phải đếm theo thứ tự (chip = mọi bước trừ chính nó, sắp theo
    thu_tu, nên bước N-1 nằm ở vị trí N-2); (2) cảnh báo **"trùng bước trước"** nổi ở mọi dòng
    (`frontend/src/pages/lsxBuoc.ts:424` so `ten` với `ten` dòng trên, mà tất cả đều là "Công đoạn");
    (3) bước Xả giấy mất nhãn đơn vị vào/ra nên bảng hiện `132 – → 325 –`.
    Đã ghi thành chip việc riêng `task_ae9163e6` kèm traceback và checklist xác minh lại bằng UI.
    Ngoài ra: các bước chế bản hiện số lượng 0 (0 bài in / 0 bản kẽm / 0 bản proof) dù quy cách tính ra
    Số kẽm 8 và Số bài in 1; bước KCS thành phẩm bị gắn cờ "đứt đơn vị" (con → cái); bước Bế gắn cờ
    "chưa chốt khuôn". Ba mục này để lại cho Task 15/17 xử lý cùng lượt giữ chỗ vật tư.
- **Task 9 — XONG (05/09/2026). Vật tư của LSX26-0005.**
  - Mở tab **Vật tư** của lệnh trước để soi: hệ ĐÃ tự gắn sẵn phần lớn BOM theo công đoạn, không phải
    khai tay từ đầu như plan giả định — TỔNG NHU CẦU 7 món, ĐỘ PHỦ 3/10 bước:
    - Bước #3 Xả giấy (Máy cắt tờ ITO 100) → **Giấy C300 · 132 tờ nguyên · NVL CHÍNH**
      (giấy bám vào bước ĂN giấy đầu tiên, tức Xả giấy, chứ không phải bước In như plan viết).
    - Bước #4 In offset → `VT-MUC-C` 0,032 kg · `VT-MUC-M` 0,032 · `VT-MUC-Y` 0,032 · `VT-MUC-K` 0,045 ·
      `VT-DM-01 Dung môi rửa máy in` 0,96 kg — tất cả PHỤ LIỆU.
    - Bước #5 Cán màng → `VT-MANG-BOPP Màng BOPP cán bóng` 0,257 kg.
  - Việc còn phải làm tay đúng một món: mở drawer **bước 100 Đếm & bó thành phẩm** → tab **Vật tư** →
    combobox "— Thêm vật tư vào công đoạn —" → chọn `VT-BANGKEO-01 · Băng keo trong 48mm (cuốn)`.
    Hệ ra `Số lượng đặt ÷ 5500 = 500 ÷ 5500 = 0,0909 cuốn` nhưng đánh dấu nguồn số là **"Đã sửa"**;
    bấm **"Đồng bộ tất cả theo công thức"** để chuyển thành **"Tự tính"** (Tổng 1 · Tự tính 1 · Đã sửa 0).
  - **Chốt khuôn bế** (đây chính là "Còn thiếu 1 mục" của lệnh — tooltip ghi *"Có công đoạn cần khuôn /
    khung mà chưa chọn"*): drawer **bước 70 Bế** → tab *Phân công & Thiết bị* → khối
    **KHUÔN CỦA BƯỚC (KHUÔN BẾ)** → chọn `KB-0002 · Khuôn bế thẻ nhân viên 54x86 — 42 con/tờ · Kệ B1`.
    Dùng lại khuôn có sẵn thay vì bấm "+ Làm khuôn mới" — đúng nghiệp vụ kho khuôn; ghi nhận lệch:
    khuôn khai 42 con/tờ còn bình bài của lệnh ra 20 con/tờ (dữ liệu seed, không sửa ở task này).
  - Cũng ở tab đó thấy khối **ĐẦU VIỆC KHOÁN LƯƠNG THỢ** của bước Bế đọc đúng ý đã bàn:
    `Bế – 150 đ/nhịp` → *"SL vào của công đoạn = 75 nhịp × 150 đ/nhịp = 11.250 đ"*.
  - Bấm **Lưu công đoạn** sau mỗi lần sửa drawer. Kết quả trên header lệnh:
    VẬT TƯ 7 → 8 → **9 món**, và badge đổi từ **"⚠ Còn thiếu 1 mục"** sang **"✓ Đủ dữ liệu"**,
    nút "Sẵn sàng lập kế hoạch" chuyển sang trạng thái bấm được.
  - **Còn treo, KHÔNG tự vá:** bước 90 KCS thành phẩm vẫn gắn cờ *"chưa chọn đầu việc"* — drawer bước Tổ
    không có ô chọn đầu việc, mà công đoạn `KCS thành phẩm` trong danh mục chưa khai đầu việc khoán nào
    (khớp cảnh báo lúc tạo lệnh DH006: "công đoạn KCS thành phẩm chưa khai công thức tính giá").
    Đây là lỗ hổng DANH MỤC, không phải lỗi thao tác lệnh. Cùng với cờ "đứt đơn vị" (con → cái) của bước
    này, để lại cho lượt rà cuối (Task 17).
- **Task 10 — XONG (05/09/2026). LSX26-0006 / DH002 "Hộp bánh 200g" 10.000 cái, hạn giao 20/9/2026.**
  - **Quy cách** (tab Quy cách → "Lưu quy cách"): giấy `C300` 300gsm · khổ nguyên 1090×790 ·
    khổ in 1090×790 · thành phẩm 530×380 · in 1 mặt · bleed 3 · khe cắt 3 · mực C M Y K mặt A.
    Hệ tính lại: **Bình bài 4 con/tờ · Số mảnh xả 1 · Số kẽm 4 · Số bài in 1**.
  - **Routing 11 bước** — mịn hơn hẳn 5 công đoạn của phiếu tính giá (In khổ vừa · Cán màng mờ · Bế ·
    Dán hộp · KCS thành phẩm): chèn thêm 6 bước chế bản + hoàn thiện + giao hàng.

    | # | Công đoạn | Loại | Tổ · Máy | Vào → Ra | Thời lượng | Tiền nhiệm |
    |---|---|---|---|---|---|---|
    | 10 | Bình bài & dàn trang | Tổ | Tổ kỹ thuật | 0 bài in → 0 bài in | — | Gốc |
    | 20 | Làm khuôn bế | Tổ | Tổ kỹ thuật | 0 bộ → 0 bộ | — | Gốc |
    | 30 | Ghi kẽm CTP | Máy | Tổ kỹ thuật · CTP Screen 8600 | 0 bản kẽm → 0 bản kẽm | 13 phút | Bình bài |
    | 40 | In proof duyệt màu | Máy | Tổ kỹ thuật · Máy in proof – 60cm | 0 bản proof → 0 bản proof | 30 phút | Bình bài |
    | 50 | In AB- Máy in-22 x 22-khổ vừa | Máy | Tổ in · Mitsubishi 4 màu 79×109 | 3.002 tờ → 2.752 tờ | 1 giờ 45 phút | Ghi kẽm + In proof |
    | 60 | cán màng mờ - cán màng 11 x 11 | Máy | Tổ cán phủ · Máy cán màng 1080 (số 1) | 2.752 → 2.672 tờ | 4 giờ 44 phút | In AB |
    | 70 | Bế | Máy | Tổ bế · Bế tự động Yawa 1050 | 2.672 tờ → 10.205 con (1 tờ = 4 con) | 1 giờ 21 phút | Làm khuôn bế + cán màng |
    | 80 | Bóc phế sau bế | Tổ | Tổ bế | 10.205 con → 10.205 con | 5 giờ 40 phút | Bế |
    | 90 | Dán hộp | Máy | Tổ dán · Dán hộp mềm máy nhỏ tự động (≤60cm) | 10.205 con → 10.000 con | 1 giờ 30 phút | Bóc phế |
    | 100 | KCS thành phẩm | Tổ | Tổ thành phẩm / KCS | 10.000 cái → 10.000 cái | — | Dán hộp |
    | 110 | Đóng thùng & dán nhãn | Tổ | Tổ giao hàng | 10.000 cái → 10.000 cái | 2 giờ 51 phút | KCS |

    Phụ thuộc đặt SAU khi đã bấm "Lưu công đoạn" lần đầu (tab Phụ thuộc chỉ liệt kê bước ĐÃ ghi DB);
    mỗi lần tick đều đọc lại trạng thái checkbox bằng JS để chắc không tick nhầm chip.
    Tổng thời gian dẫn **18 giờ 35 phút** ≈ 2,3 ngày làm việc; nhanh–chậm 13 giờ 36 – 27 giờ 13;
    dự kiến xong 8/9/2026, còn 15 ngày tới hạn.
  - **Vật tư** — hệ tự suy từ danh mục công đoạn gần đủ, chỉ thêm tay đúng một món:
    - Bước 50 In AB → `VT-MUC-C` 0,905 kg · `VT-MUC-M` 0,905 · `VT-MUC-Y` 0,905 · `VT-MUC-K` 1,293 ·
      `VT-DM-01 Dung môi rửa máy in` 0,48 kg (5 món, đều "Tự tính").
    - Bước 60 Cán màng → `VT-MANG-BOPP` 34,835 kg.
    - Bước 70 Bế → 0 vật tư (bế ăn khuôn, không ăn vật tư).
    - Bước 90 Dán hộp → `VT-KEO-01 Keo dán hộp` 10 kg.
    - Bước 110 Đóng thùng → `VT-THUNG-01` 100 cái · `VT-BANGKEO-01` 1,818 cuốn; **thêm tay**
      `VT-DAY-01 Dây đai PP 12mm` → hệ ra `10.000 ÷ 28.500 = 0,351 cuốn`.
  - **Chốt khuôn bế** — lệnh này CÓ bước "Làm khuôn bế" nên đúng nghiệp vụ là làm khuôn mới chứ không
    mượn kho: drawer bước 70 → *Phân công & Thiết bị* → **KHUÔN CỦA BƯỚC (KHUÔN BẾ)** → **"+ Làm khuôn mới"**
    → tên `Khuôn bế hộp bánh 200g 530x380 — 4 con/tờ`, ngày có khuôn (dự kiến) `07/09/2026` → **"Tạo khuôn"**.
    Hệ sinh **`KB-0003`** ở tình trạng *"Đang làm — dự kiến có ngày 07/09/2026. Bước này chưa chạy được."*
    (đúng ý: khuôn chưa về thì bước Bế chưa xếp lịch chạy được).
  - Cũng ở tab đó, **ĐẦU VIỆC KHOÁN LƯƠNG THỢ** của bước Bế đọc: `Bế – 150 đ/nhịp` →
    *"SL vào của công đoạn = 2.672 nhịp × 150 đ/nhịp = 400.800 đ"*.
  - **Kết quả header sau "Lưu công đoạn"**: SL ĐẶT 10.000 cái · VÀO MÁY 3.002 tờ · GIẤY NGUYÊN 3.002 tờ ·
    BÌNH BÀI 4 con · CÔNG ĐOẠN 11 · **VẬT TƯ 12 món** · HẠN GIAO 20/9/2026 · CÔNG THỢ 6.876.847 đ,
    badge **"⚠ Còn thiếu 1 mục" → "✓ Đủ dữ liệu"**, nút "Sẵn sàng lập kế hoạch" bấm được.
  - **Ghi nhận lệch danh mục (không tự vá):** công đoạn *"cán màng mờ"* lại khai định mức trỏ vào
    `VT-MANG-BOPP · Màng BOPP cán BÓNG` chứ không phải `VT-MANG-MO`. Sửa thì mất công thức đang gắn,
    nên để nguyên và gộp vào lượt rà danh mục cuối (Task 17).
  - Bước 100 KCS thành phẩm vẫn treo cờ "đứt đơn vị" (con → cái) như LSX26-0005 — cùng một lỗ hổng danh mục.

### Task 11 — DH003 Sách (nhánh vật tư thay thế) — XONG PHẦN LÀM ĐƯỢC, CÒN 1 CHẶN CỨNG

**Lệnh Bìa `LSX26-0007`** (đã ghi ở lượt trước, nhắc lại kết quả để đối chiếu): quy cách C250 ·
khổ nguyên 1090×790 · khổ in 1090×790 · thành phẩm 332×240 · 1 mặt · bình bài **9** · số kẽm 4;
routing **6 bước** đúng bảng; vật tư **7 món**, dòng chính đọc **`Giấy C250 · 553 tờ nguyên · NVL CHÍNH`**
→ nghiệm thu "lệnh Bìa dùng C250 chứ không phải C300" **ĐẠT**.

**Lệnh Ruột `LSX26-0008`** — lệnh xuống kế hoạch với quy cách RỖNG (0×0, chưa chọn giấy, 0 công đoạn)
vì dòng đơn DH003 không trỏ vào phiếu thành phần nào (`_tinh_dong` trả `quy_cach=None`, `routing=[]`
khi `tp is None`). Dựng tay toàn bộ:

- **Quy cách** (tab Quy cách → gõ từng ô → "Lưu thay đổi"): Giấy `C150 · 150 gsm` · khổ giấy nguyên
  650×980 · khổ in 650×980 · thành phẩm 160×240 · cách in **2 mặt (AB)** · bleed 0 · khe cắt 0 ·
  mực **K mặt A + K mặt B** → dòng chú thích "1 + 1 = 2 kẽm mỗi tay". Máy tự tính ra: BÌNH BÀI **16** ·
  SỐ MẢNH XẢ 1 · SỐ KẼM 2 · CÁCH BÌNH "Máy tự bình" · sơ đồ bình khổ hiệu suất 97%, 4×4.
- **Routing 10 bước** (tab Công đoạn → "Bảng danh sách" → "+ Thêm công đoạn" rồi "Chèn công đoạn mới
  sau bước 1" ×9 → mở từng dòng chọn công đoạn + loại bước):

  | # | Công đoạn | Loại | Tổ (hệ tự gán) | Máy | Vào → Ra | Thời lượng |
  |---|---|---|---|---|---|---|
  | 10 | Bình bài & dàn trang | Tổ | Tổ kỹ thuật | — | 0 bài in → 0 bài in | — |
  | 20 | Ghi kẽm CTP | Máy | Tổ kỹ thuật | CTP Screen 8600 (Nhật) | 0 bản kẽm → 0 bản kẽm | 7 phút |
  | 30 | In AB- Máy in-22 x 22-khổ vừa | Máy | Tổ in | Máy 4 màu Mitsubishi 79×109 | 368 tờ → 168 tờ | 1 giờ 19 phút |
  | 40 | Cắt demi / chia tờ | Tổ | Tổ cắt | — | 168 tờ → 138 tờ | 3 phút |
  | 50 | Gấp tay | Tổ | Tổ thành phẩm / KCS | — | 138 tờ → 133 tay sách | 2 phút |
  | 60 | Bắt tay | Tổ | Tổ thành phẩm / KCS | — | 133 tay sách → 2.083 cái | 5 phút |
  | 70 | Vào bìa keo nhiệt | Tổ | Tổ thành phẩm / KCS | — | 2.083 cái → 2.041 cái | 2 giờ 16 phút |
  | 80 | Xén 3 mặt | Tổ | Tổ cắt | — | 2.041 cái → 2.000 cái | 48 phút |
  | 90 | KCS thành phẩm | Tổ | Tổ thành phẩm / KCS | — | 2.000 cái → 2.000 cái | — |
  | 100 | Đếm & bó thành phẩm | Tổ | Tổ thành phẩm / KCS | — | 2.000 cái → 2.000 cái | 1 giờ |

  Đầu việc khoán hệ tự chọn đúng cho 9/10 bước (Bình bài 45.000 đ/bài in · Bình bài và ra kẽm
  15.000 đ/bản kẽm · Cắt demi 12 đ/tờ · Gấp tay 120 đ/tay sách · Bắt tay 50 đ/tay sách · Vào bìa keo
  nhiệt 1.200 đ/cuốn · Xén 3 mặt 400 đ/cuốn · Đếm & bó 900 đ/bộ). Riêng **KCS thành phẩm KHÔNG có
  đầu việc khoán nào** — đúng lỗ hổng danh mục đã ghi ở Task 9/10. CÔNG THỢ tổng **3.349.026 đ**.
- **Phụ thuộc**: sau "Lưu công đoạn" lần đầu mới có danh sách; tick chuỗi thẳng 10→20→…→100, mỗi
  lần đọc lại checkbox bằng JS để chắc đúng vị trí (nhãn chip vẫn hiện trơ chữ "Công đoạn" — bug
  `mac-dinh-buoc` cũ). Cột "Cần xem lại" sau khi lưu hiện đúng tên bước tiền nhiệm cho cả 9 bước.
  Ghi nhận thêm: tab Phụ thuộc còn liệt kê **nhóm `LSX26-0007`** (6 bước của lệnh Bìa) — hệ cho
  phép nối phụ thuộc chéo lệnh trong cùng đơn; lần này không dùng.
- **Vật tư — 8 món**: bước 30 In → `Giấy C150 368 tờ nguyên (NVL CHÍNH)` + `VT-MUC-C/M/Y/K` +
  `VT-DM-01`; bước 70 Vào bìa keo nhiệt → **`VT-KEOPUR-01 Keo gáy nhiệt PUR` 4,082 kg** (danh mục
  gắn PUR chứ không phải `VT-KEO-01` như plan dự kiến — PUR đúng nghiệp vụ hơn, giữ nguyên);
  bước 100 Đếm & bó → **thêm tay `VT-BANGKEO-01 Băng keo trong 48mm`** → hệ ra
  `2.000 ÷ 5.500 = 0,3636 → 0,364 cuốn`.
  *Lệch danh mục:* bài in 1+1 (chỉ mực K) nhưng định mức công đoạn "In offset" vẫn kéo đủ 4 mực
  C/M/Y/K. Cùng họ với lỗi `cán màng mờ → VT-MANG-BOPP`; gộp vào lượt rà danh mục cuối, không tự vá.

**CHẶN CỨNG — không có đường UI để gỡ.** Badge lệnh vẫn đứng ở *"Còn thiếu 1 mục"*, mở ra đọc:
**"Chưa khai Số trang / Trang mỗi tay — có công đoạn đổi tay sách → cái"**. Nút *"Sẵn sàng lập kế
hoạch"* bị `disabled` cứng theo `d.thieu.length > 0` (`frontend/src/pages/LsxDetailView.tsx:784`).

- Nguyên nhân: hai ô **Số trang / Trang mỗi tay** ở tab Quy cách chỉ render khi
  `(form.qc.so_trang ?? 1) > 1` (`LsxDetailView.tsx:1261`), mà lệnh này xuống với `so_trang` rỗng.
  Backend thì NHẬN được: `so_trang`/`trang_moi_tay` nằm trong `LsxService._QC_SUA_DUOC`
  (`backend/app/services/lsx_service.py:2562`). Tức chỉ frontend khoá, không phải nghiệp vụ khoá.
- Hệ quả số học: `so_to_per_sp` kẹt ở **1** thay vì **6** (192 trang ÷ 32 trang/tay), nên bước In chỉ
  ra **368 tờ** trong khi phiếu tính giá PTG-2026-0003 khai **13.360 tờ C150**. Cả nhánh "bắt tay →
  cái" cũng sai thang: hệ quy `1 tay sách = 16 cái` (lấy bình bài) thay vì `6 tay = 1 cuốn`.
- Không có cửa nào khác: `Bình bài` (`so_con`) có `min={1}` nên nhiều nhất chỉ đưa vào máy về 2.000
  tờ; sửa ở phiếu tính giá rồi tạo lại lệnh cũng vô ích vì dòng đơn DH003 không gắn phiếu thành phần.
- **Ảnh hưởng plan:** `LSX26-0008` (và sẽ là `LSX26-0004` của DH005 ở Task 12) KHÔNG bấm được
  "Sẵn sàng lập kế hoạch" ở Task 17, và nhu cầu C150 của hai lệnh này thiếu ~6 lần. Nhánh "kho thiếu
  phải mua" vẫn còn sống nhờ `LSX26-0010` của DH006 (13.365 tờ C150 ≈ 1.277 kg > tồn 800 kg).

- **Task 12 — XONG (05/09/2026). DH005 · Công ty TNHH Giáo dục Trí Việt · PO-TV-2026-005 · BG26-0005 v1
  · hạn giao 30/9/2026. Hai lệnh `LSX26-0003` (Bìa sách) + `LSX26-0004` (Ruột sách 192 trang),
  mỗi lệnh 2.000 cuốn, dựng tay từ quy cách rỗng.**

  **`LSX26-0003` — Bìa sách (nhánh THUÊ NGOÀI).**
  - Quy cách: giấy `C300 · 300 gsm` · khổ nguyên 1090×790 · khổ in 1090×790 · thành phẩm 332×240 ·
    cách in **1 mặt** · mực C+M+Y+K mặt A ⇒ hệ ra **BÌNH BÀI 9 con/tờ · SỐ MẢNH XẢ 1 · SỐ KẼM 4**.
    Header đổi từ "Còn thiếu 3 mục" → "Còn thiếu 1 mục" → sau khi có routing thì **"Đủ dữ liệu"**.
  - Routing 6 bước (Bảng danh sách → "Thêm công đoạn" → "Chèn công đoạn mới sau bước 1" ×5, rồi mở
    drawer chọn công đoạn cho từng bước bằng mũi tên "Bước sau"):

    | # | Công đoạn | Loại | Tổ · Máy | Vào → Ra | Thời lượng | Tiền nhiệm |
    |---|---|---|---|---|---|---|
    | 10 | Bình bài & dàn trang | Tổ | Tổ kỹ thuật | 0 bài in → 0 bài in | — | Gốc |
    | 20 | Ghi kẽm CTP | Máy | Tổ kỹ thuật · CTP Screen 8600 (Nhật) | 0 bản kẽm → 0 bản kẽm | 13 phút | Bình bài |
    | 30 | In proof duyệt màu | Máy | Tổ kỹ thuật · Máy in proof – 60cm | 0 bản proof → 0 bản proof | 30 phút | Ghi kẽm CTP |
    | 40 | In AB- Máy in-22 x 22-khổ vừa | Máy | Tổ in · Máy 4 màu Mitsubishi 79×109 | 553 tờ → 353 tờ | 1 giờ 21 phút | In proof |
    | 50 | cán màng mờ - cán màng 11 x 11 | **Máy (thuê ngoài)** | Tổ cán phủ · **Máy cán màng 1080 — thuê ngoài – Cơ sở Tân Phát** | 353 tờ → 303 tờ | 1 giờ 21 phút | In AB |
    | 60 | Cắt thành phẩm | Máy | Tổ cắt · Máy cắt tờ Kyodo 132 | 303 tờ → 2.000 con (1 tờ = 9 con) | 1 giờ | cán màng |

    Tổng thời gian dẫn **4 giờ 25 phút** · dự kiến xong 6/9/2026 · còn 25 ngày tới hạn giao.
    Header: SL ĐẶT 2.000 cuốn · VÀO MÁY 553 tờ · GIẤY NGUYÊN 553 tờ · BÌNH BÀI 9 con · CÔNG ĐOẠN 6 ·
    VẬT TƯ **7 món** · CÔNG THỢ **708.825 đ**.
  - **Bước thuê ngoài làm ĐÚNG theo chỉ đạo mới, KHÔNG dùng loại bước "Thuê ngoài"** (loại đó đã ẩn):
    bước 50 để **Loại bước = Máy**, gắn máy `86 · Máy cán màng 1080 — thuê ngoài – Cơ sở Tân Phát`
    trong danh mục máy, nhập liệu y hệt một bước máy thường (vẫn có tổ, vẫn có "Số người bố trí (kế
    hoạch)" — ô này `min=1` nên không hạ về 0 được). Điểm khác duy nhất: **xoá ô "Đầu việc khoán
    lương thợ"** (từ `Cán màng — 1.200 đ/m²` về "— chọn đầu việc khoán —") ⇒ CÔNG THỢ tụt
    1.073.587 đ → **708.825 đ**, tức bước này không sinh tiền khoán. Text Task 12 Bước 2 ở trên
    (viết "Loại bước thực hiện = Thuê ngoài") ĐÃ LỖI THỜI, giữ lại để đối chiếu.
  - **Hệ quả phải bù tay:** vật tư của một bước lấy theo **đầu việc khoán**, nên xoá đầu việc là mất
    luôn BOM của bước đó. Đã thêm tay ở tab Vật tư của bước 50: `VT-MANG-MO Màng BOPP cán mờ`, hệ tự
    ra công thức `SL vào × Dài tờ in × Rộng tờ in × 0.0147 = 353 × 1,09 × 0,79 × 0,0147 = 4,468 kg`.
    Chọn `VT-MANG-MO` chứ không phải `VT-MANG-BOPP` (bóng) như plan viết — công đoạn là *cán màng
    **mờ***; đây cũng chính là lỗi danh mục đã ghi ở Task 11, nay né bằng cách khai tay.
  - BOM 7 món: `Giấy C300 553 tờ nguyên` (NVL chính) + `VT-MUC-C/M/Y/K` (0,167/0,167/0,167/0,238 kg)
    + `VT-DM-01` 0,48 kg + `VT-MANG-MO` 4,468 kg.

  **`LSX26-0004` — Ruột sách 192 trang.** Dựng y hệt `LSX26-0008` của DH003.
  - Quy cách: `C150 · 150 gsm` · nguyên 650×980 · in 650×980 · thành phẩm 160×240 · **2 mặt (AB)** ·
    mực K mặt A + K mặt B ("1 + 1 = 2 kẽm mỗi tay") ⇒ **BÌNH BÀI 16 · MẢNH XẢ 1 · SỐ KẼM 2**.
  - Routing 10 bước, chuỗi phụ thuộc thẳng 10→20→…→100, số liệu trùng khít `LSX26-0008`:
    Bình bài & dàn trang (Tổ) · Ghi kẽm CTP (Máy · CTP Screen 8600) · In AB khổ vừa (Máy · Mitsubishi
    79×109, 368 tờ → 168 tờ, 1 giờ 19 phút) · Cắt demi / chia tờ (Tổ, 168 → 138) · Gấp tay (138 tờ →
    133 tay sách) · Bắt tay (133 tay sách → 2.083 cái) · Vào bìa keo nhiệt (2.083 → 2.041, 2 giờ 16
    phút) · Xén 3 mặt (2.041 → 2.000, 48 phút) · KCS thành phẩm · Đếm & bó thành phẩm (1 giờ).
    Tổng thời gian dẫn **5 giờ 48 phút** · dự kiến xong 8/9/2026. CÔNG THỢ **3.349.026 đ** —
    khớp từng đồng với `LSX26-0008`, xác nhận hai lệnh cùng khuôn.
  - Vật tư **8 món**: bước 30 In → `Giấy C150 368 tờ nguyên` + 4 mực + `VT-DM-01` 0,24 kg; bước 70
    → `VT-KEOPUR-01` 4,082 kg; bước 100 → **thêm tay `VT-BANGKEO-01` = 2.000 ÷ 5.500 = 0,364 cuốn**.
  - **Lặp lại đúng chặn cứng của `LSX26-0008`:** badge đứng ở "Còn thiếu 1 mục" (Chưa khai Số trang /
    Trang mỗi tay) ⇒ `so_to_per_sp` kẹt ở 1, In chỉ ra 368 tờ thay vì ~13.360, và nút "Sẵn sàng lập
    kế hoạch" bị disable. Cùng một gốc `LsxDetailView.tsx:1261` / `:784` — không tự vá, đã treo ở
    chip `task_826e8706`.

  **Ghi thêm — lệch danh mục mới thấy ở Task 12 (chưa vá, gom vào lượt rà cuối):**
  - Ba bước chế bản (`Bình bài & dàn trang`, `Ghi kẽm CTP`, `In proof duyệt màu`) đều ra **0** ở ô
    "Số lượng ra" vì ô này read-only, ghi "Theo công thức sản lượng của bước" mà công thức trong danh
    mục công đoạn chưa khai — dù quy cách đã có SỐ KẼM 4 và BÌNH BÀI 9. Hệ quả: tiền khoán
    `Bình bài & ra kẽm 15.000 đ/bản kẽm` tính ra 0 đ.
  - Bước `Cắt thành phẩm` gắn `Máy cắt tờ Kyodo 132` hiện dải nhanh–chậm **126 giờ 35 phút – 303 giờ
    20 phút** cho 303 tờ ⇒ tốc độ máy trong danh mục đang khai cỡ 1–2,4 đơn vị/giờ, sai thang khoảng
    ba bậc. Cùng họ với chip `task_8373c0fb` (ô tốc độ min/max của máy không sửa được trên UI).

- **Task 13 — TẠM DỪNG.** DH004 vẫn NHÁP: dòng đơn không trỏ vào phiếu thành phần nào sống
  (`PhieuThanhPhan` 27/28 mồ côi), không có cửa UI để nối lại. Nhánh này park theo đúng ghi chú ở
  Task 11; các nhánh còn lại không phụ thuộc vào nó.

- **Task 14 — XONG (05/09/2026). DH006 · Công ty TNHH Điện tử Sao Mai · PO-SM-2026-006 · BG26-0006 v1
  · hạn giao 30/9/2026. Hai lệnh `LSX26-0009` (Bìa sách) + `LSX26-0010` (Ruột sách 192 trang), mỗi
  lệnh 2.000 cái, rồi bài ghép `GB26-0001`.**

  **`LSX26-0009` — Bìa sách.** Lệnh xuống kế hoạch với 3 bước kế thừa; nới lên **6 bước** đúng bảng
  Bìa: `Bình bài & dàn trang` (Tổ) · `Ghi kẽm CTP` (Máy — CTP Screen 8600) · `In proof duyệt màu`
  (Máy — Máy in proof 60cm) · `In AB- Máy in-22 x 22-khổ vừa` (Máy — Máy 4 màu Mitsubishi 79×109) ·
  `cán màng mờ` (Máy — **Máy cán màng 1080 (số 1)**, làm trong nhà, khác hẳn lệnh Bìa của DH005) ·
  `Cắt thành phẩm` (Máy — Máy cắt tờ Kyodo 132). Chuỗi phụ thuộc thẳng 10→60, badge **Đủ dữ liệu**,
  vật tư **7 món**, CÔNG THỢ **1.073.587 đ** trước khi ghép. Quy cách đọc lại để đối chiếu với
  `LSX26-0003`: `C300 · 1090×790 · TP 332×240 · 1 mặt · 4/0 · bình bài 9 · số kẽm 4 · 553 tờ` —
  **trùng khít**, nên đây là cặp ghép hợp lệ thay cho cặp DH004 mà plan dự kiến (DH004 đã park).

  **`LSX26-0010` — Ruột sách 192 trang.** Lệnh này kế thừa `PTG-2026-0003` nên `so_to_per_sp` = **6**
  (đúng 192 trang ÷ 32 trang/tay) — KHÔNG dính chặn cứng Số trang như `LSX26-0004`/`LSX26-0008`.
  Xuống kế hoạch với 6 bước (In AB → Gấp tay → Bắt tay → Vào bìa keo nhiệt → Xén 3 mặt → KCS), tất cả
  loại "Máy", chưa gán máy. Dựng lại thành **10 bước** bằng "Chèn công đoạn mới sau bước N" ×3 +
  "Chuyển bước 1 xuống" ×2, rồi mở từng dòng khai công đoạn/loại bước:

  | # | Công đoạn | Loại | Tổ (hệ tự gán) | Máy | Vào → Ra | Thời lượng |
  |---|---|---|---|---|---|---|
  | 10 | Bình bài & dàn trang | Tổ | Tổ kỹ thuật | — | 0 bài in → 0 bài in | — |
  | 20 | Ghi kẽm CTP | Máy | Tổ kỹ thuật | CTP Screen 8600 (Nhật) | 0 bản kẽm → 0 bản kẽm | 40 phút |
  | 30 | In AB- Máy in-22 x 22-khổ vừa | Máy | Tổ in | Máy 4 màu Mitsubishi 79×109 | 13.395 tờ → 13.045 tờ | 5 giờ 43 phút |
  | 40 | Cắt demi / chia tờ | Tổ | Tổ cắt | — | 13.045 tờ → 13.015 tờ | 4 giờ 21 phút |
  | 50 | Gấp tay | Tổ | Tổ thành phẩm / KCS | — | 13.015 tờ → 12.754 tay sách | 1 giờ 25 phút |
  | 60 | Bắt tay | Tổ | Tổ thành phẩm / KCS | — | 12.754 tay sách → 2.083 cái | 2 giờ 8 phút |
  | 70 | Vào bìa keo nhiệt | Tổ | Tổ thành phẩm / KCS | — | 2.083 cái → 2.041 cái | 1 giờ 8 phút |
  | 80 | Xén 3 mặt | Tổ | Tổ cắt | — | 2.041 cái → 2.000 cái | 24 phút |
  | 90 | KCS thành phẩm | Tổ | Tổ thành phẩm / KCS | — | 2.000 cái → 2.000 cái | — |
  | 100 | Đếm & bó thành phẩm | Tổ | Tổ thành phẩm / KCS | — | 2.000 cái → 2.000 cái | 1 giờ |

  Phụ thuộc: 4 bước mới tick tay (20←10, 30←20, 40←30, 100←90); bước 50 phải **bỏ tick `In AB`** kế
  thừa rồi tick `Cắt demi / chia tờ` cho đúng chuỗi mới; các bước 60–90 đã có sẵn chuỗi kế thừa
  đúng. Sau khi lưu, cột "Tiền nhiệm" đọc đúng tên bước trước ở cả 9 bước; bước 20 hiện cờ
  *"trùng bước trước"* (thông tin, không phải lỗi). Vật tư **8 món** (thêm tay
  `VT-BANGKEO-01 Băng keo trong 48mm` ở bước 100 → 0,364 cuốn), `Giấy C150 13.395 tờ nguyên` —
  đúng nhánh "kho thiếu phải mua" (≈1.277 kg > tồn 800 kg). Badge **Đủ dữ liệu**, CÔNG THỢ
  **6.124.795 đ**.

  **Bài ghép `GB26-0001`.** Sản xuất → Bài ghép → tab "Lệnh chờ ghép" (7 lệnh) → tick `LSX26-0009`
  + `LSX26-0003` → thanh dưới đọc *"Đã chọn 2 lệnh · Cùng chất liệu: Giấy C300"* → "Tạo bài ghép (2)".
  Trong tab Công đoạn của bài, chọn nút bước **#40 In AB** của cả hai lệnh → thanh nổi
  *"Đã chọn 2 bước · In AB- Máy in-22 x 22-khổ vừa"* → "Gộp 2 bước". Lượt chạy chung khai lại:
  Tổ **Tổ in** · Máy **Máy 4 màu Mitsubishi 79×109** · đầu việc khoán **In offset — 25 đ/tờ**; vật tư
  của lượt chung giữ nguyên 5 món (4 mực + dung môi) → "Lưu kế hoạch lượt chung".
  - Ngay sau khi gộp, băng "Còn thiếu" vẫn báo **"Diện tích thành phẩm vượt quá tờ ghép"** vì mỗi
    lệnh còn giữ 9 con/tờ (9+9=18 con × 332×240 > tờ 1090×790). Sửa ở ô "CON TRÊN TỜ" của từng lệnh:
    **4 + 4**. Băng cảnh báo tắt, `LẤP ĐẦY TỜ` = **74%**.
  - Kết quả bài ghép: SỐ LỆNH 2 · TỜ CHẠY **630** · GIẤY LĨNH KHO **830** · HAO SETUP 200 tờ ·
    TỶ LỆ HAO 31,7% · SỐ KẼM **4** · SỐ MÀU 4/0 · BƯỚC CHUNG 1 · KHOÁN BƯỚC CHUNG **20.750 đ**
    (830 tờ × 25 đ). Mỗi lệnh chiếm 50% giấy = 415 tờ, ra 2.120/2.000.
  - **Nghiệm thu "ghép rẻ hơn chạy riêng":** chạy riêng là 553 + 553 = **1.106 tờ C300** và
    4 + 4 = **8 bản kẽm**; ghép còn **830 tờ** và **4 bản kẽm** ⇒ bớt 276 tờ giấy (−25%) và 4 kẽm.
  - Cả hai lệnh Bìa hiện băng ở tab Công đoạn: *"Bước in do bài ghép **GB26-0001** điều phối —
    chưa chọn máy · 4 con/tờ · khổ 1090×790. Máy, giấy, khổ tờ và số con sửa tại bài."* Header hai
    lệnh cùng đổi VÀO MÁY/GIẤY NGUYÊN 553 → **630 tờ**; CÔNG THỢ `LSX26-0003` 708.825 → **710.750 đ**,
    `LSX26-0009` 1.073.587 → **1.361.742 đ**. Danh sách Bài ghép: "Lệnh chờ ghép 5 · Bài ghép đã tạo 1".

  **Lệch phát hiện thêm ở Task 14 (chưa vá):**
  - Băng bài ghép trên lệnh vẫn ghi *"chưa chọn máy"* dù lượt chạy chung ĐÃ gán Máy 4 màu
    Mitsubishi 79×109 và đã lưu — băng đọc máy từ bước của lệnh chứ không đọc từ lượt chung.
  - `LSX26-0010` KHÔNG xuất hiện trong danh sách "Lệnh chờ ghép" (7 lệnh liệt kê gồm 0003–0009 nhưng
    thiếu 0010), trong khi `LSX26-0004`/`LSX26-0008` cùng loại Ruột C150 1/1 thì có. Chưa truy nguyên.

  **Ghi chú thao tác (để lần sau khỏi mất công):** một loạt thay đổi routing của `LSX26-0010` đã bị
  **mất trắng** vì lỡ điều hướng khỏi trang khi chưa bấm "Lưu công đoạn" — bảng công đoạn là form
  nháp phía client, rời trang là mất. Đã dựng lại từ đầu và từ đó lưu ngay sau mỗi mốc.

### Task 17 (chạy TRƯỚC Task 15) — chuyển lệnh sang "Sẵn sàng lập kế hoạch"

**Quyết định lệch thứ tự (ruling):** Task 15 không chạy được nếu lệnh còn ở trạng thái *Nháp lệnh*.
Màn **Kế hoạch vật tư** chỉ gom nhu cầu của lệnh **Sẵn sàng / Đã lập kế hoạch / Đã phát hành**
(chú thích ngay dưới tiêu đề màn), nên khi cả 8 lệnh còn nháp thì bảng cân đối rỗng
("Chưa có nhu cầu vật tư nào cần cân đối"). Vì vậy **Bước 1-3 của Task 17 phải chạy trước Task 15**.
Đây là lỗi thứ tự của bản kế hoạch, không phải lỗi phần mềm.

- Đã bấm **"Sẵn sàng lập kế hoạch"** trên 6 lệnh: `LSX26-0003`, `0005`, `0006`, `0007`, `0009`, `0010`.
- `LSX26-0004` và `LSX26-0008` vẫn **Nháp**: nút bị `disabled` do còn dòng vật tư thiếu định mức
  (chặn cứng ở `frontend/src/pages/LsxDetailView.tsx:784` — `disabled={d.thieu.length > 0}`).
  Đã bấm thật vào nút, không có gì xảy ra, trạng thái giữ nguyên Nháp.
- Vì chỉ có 8 lệnh (không phải 10 như plan giả định), bộ lọc "Sẵn sàng" đếm **6**, không phải 10.

### Task 15 — Cân đối & giữ chỗ vật tư

Màn **Kế hoạch vật tư → Theo mặt hàng**, 15 dòng. Bốn dòng ĐỎ (thiếu):

| Vật tư | Tồn | Cần | Thiếu |
|---|---|---|---|
| Giấy C150 | 800 kg | 1.279,89 kg | **−479,89 kg** |
| Giấy C300 | 500 kg | 1.012,06 kg | **−512,06 kg** |
| Keo gáy nhiệt PUR | 0 kg | 4,08 kg | **−4,08 kg** |
| Màng BOPP cán mờ | 0 kg | 4,47 kg | **−4,47 kg** |

11 dòng còn lại đủ 100% (Giấy C250, Băng keo trong 48mm, Dây đai PP 12mm, Dung môi rửa máy in,
Keo dán hộp, Màng BOPP cán bóng, 4 mực offset, Thùng carton 5 lớp).

Tab **Theo lệnh sản xuất** — bấm **Giữ chỗ** lần lượt 7 dòng, kết quả đúng hình dạng plan mong đợi:

- Giữ đủ → **Mở khóa**: `LSX26-0007` 7/7 · `GB26-0001` 6/6 · `LSX26-0009` 1/1.
- Giữ dở → **Chờ bù tồn**: `LSX26-0005` 7/8 · `LSX26-0006` 10/11 · `LSX26-0010` 6/8 · `LSX26-0003` 0/1.

Giữ chỗ cấp theo **thứ tự dòng**: lệnh nào chạm đáy tồn thì ôm chip đỏ và kẹt lại.

**Lệch phát hiện ở Task 15 (chưa vá):** `LSX26-0005` chỉ giữ được một phần "Mực in offset Đen
0,04 kg" (chip vàng) trong khi tồn mực Đen là 60 kg còn tổng nhu cầu toàn bộ chỉ 10,33 kg.

### Task 16 — Mua bù thiếu (ĐANG DỞ — bị chặn ở bước duyệt)

**Bước 1-2 — lập yêu cầu mua từ Kế hoạch vật tư (XONG).** Bấm nút **Mua (N)** ở cột thao tác của
từng dòng lệnh, app nhảy sang Thu mua → Yêu cầu mua hàng kèm modal điền sẵn:

| Phiếu | Nguồn | Món |
|---|---|---|
| `YCMH-260905-OWEQ` | LSX26-0006 | Giấy C300 512,06 kg |
| `YCMH-260905-VB5C` | LSX26-0010 | Giấy C150 479,9 kg · Keo gáy nhiệt PUR 4,09 kg |
| `YCMH-260905-1D0T` | LSX26-0003 | Màng BOPP cán mờ 4,47 kg |

Ngày cần hàng đặt **12/09/2026** cho cả ba (giá trị điền sẵn là 04/09/2026 — hôm nay).

**Hai lỗi chặn gặp phải, đã tự xử:**
1. Ô SỐ LƯỢNG của modal có `step` 2 số lẻ, nhưng app điền sẵn số **3 số lẻ** lấy thẳng từ bảng
   cân đối (512.057 / 479.892 / 4.082 / 4.468) ⇒ trình duyệt chặn submit với
   *"Vui lòng nhập giá trị hợp lệ. Hai giá trị hợp lệ gần nhất là 512,05 và 512,06."*
   Phải sửa tay thành 512.06 / 479.9 / 4.09 / 4.47. **Đây là lỗi: app tự điền số nó tự từ chối.**
2. Lưu `YCMH` cho LSX26-0010 trả lỗi server *"Vật tư chưa được nhà cung cấp nào khai báo. Vui lòng
   khai mặt hàng trong Nhà cung cấp trước khi tạo yêu cầu mua."* Nguyên nhân: **Màng BOPP cán mờ**
   và **Keo gáy nhiệt PUR** không có trong bảng giá của NCC nào. Đã vào Thu mua → Nhà cung cấp →
   *Công ty TNHH Bao bì Tân Phát* → tab **Bảng giá vật tư** → "+ Thêm mặt hàng" hai dòng:
   `Màng BOPP cán mờ` (VT-MANG-MO) kg — 95.000 đ và `Keo gáy nhiệt PUR` (VT-KEOPUR-01) kg —
   165.000 đ → "Lưu nhà cung cấp" (NCC từ 5 → **7 mặt hàng**).
   - Phụ: ô gợi ý vật tư **không khớp khi gõ đủ dấu** — gõ "BOPP cán mờ" báo *"Không có trong danh
     mục"*, gõ "BOPP" mới ra. Cần xem lại hàm chuẩn hoá chuỗi tìm kiếm.

**Bước 3-4 — lập đơn mua hàng (XONG phần lập, DỞ phần duyệt).** Thu mua → Mua hàng → tab
"Yêu cầu chờ xử lý", mở từng YCMH, app dựng sẵn "Đơn mua hàng mới" và tự chọn NCC theo bảng giá:

| Đơn | Nguồn | NCC | Tiền |
|---|---|---|---|
| `DMH-260905-WYS8` | YCMH-…-OWEQ | Giấy Vĩnh Tiến | 10.753.260 đ |
| `DMH-260905-2VOH` | YCMH-…-VB5C | Giấy Vĩnh Tiến | 10.557.800 đ |
| `DMH-260905-IGM4` | YCMH-…-VB5C | Bao bì Tân Phát | 674.850 đ |
| `DMH-260905-3G0X` | YCMH-…-1D0T | Bao bì Tân Phát | 424.650 đ |

Một YCMH 2 món của hai NCC khác nhau tự tách thành **2 đơn** — đúng nghiệp vụ.
Đã bấm **"Gửi duyệt"** cả 4 đơn → cả 4 chuyển **Nháp → Chờ duyệt**.

**CHẶN CỨNG:** Kế toán → Đơn mua hàng, bấm **Duyệt** trả lỗi
*"Nguoi lap phieu khong duoc tu duyet phieu cua chinh minh."* Admin là người lập nên không tự duyệt
được — đúng thiết kế "Hai bước, hai người". Người duyệt hợp lệ là tài khoản `lequangdao`
(NV009 · Ban giám đốc · Giám đốc · TK003, vai trò **Giám đốc** đã gán sẵn). Đã bấm
"Đặt lại mật khẩu" trong Hồ sơ nhân sự → app cấp mật khẩu tạm và **thu hồi mọi phiên**.
Việc đăng nhập bằng tài khoản đó phải do người dùng tự làm — trợ lý không được gõ mật khẩu vào form.

**Còn nợ của Task 16:** duyệt 4 đơn → Kho hàng → Yêu cầu nhập xuất lập phiếu nhập cho 4 lô, ghi sổ →
quay lại Kế hoạch vật tư xác nhận tồn tăng và 4 dòng đỏ tắt → bật lại Giữ chỗ cho
`LSX26-0003`, `0005`, `0006`, `0010`.

### Task 16 — bước 4-7 (XONG, đăng nhập `lequangdao`)

**Bước 4 — duyệt đơn.** Người dùng đăng nhập `lequangdao` (Giám đốc). Kế toán → Đơn mua hàng,
bấm **Duyệt** lần lượt 4 đơn `DMH-260905-WYS8`, `-2VOH`, `-IGM4`, `-3G0X` → cả 4 sang **Đã duyệt**.
Chốt tách vai ở `purchase_service.approve` không miễn cho giám đốc, nhưng ở đây người lập là Admin
nên giám đốc duyệt được.

**Bước 5 — yêu cầu nhập + phiếu nhập kho.** Kho hàng → Yêu cầu nhập xuất → "+ Tạo yêu cầu":
ngày cần nhập 12/09/2026, 4 dòng (Giấy C300 512,06 · Giấy C150 479,9 · Keo gáy nhiệt PUR 4,09 ·
Màng BOPP cán mờ 4,47) kèm đơn giá 21.000 / 22.000 / 165.000 / 95.000 đ. Ra **`DNN00004`**,
tổng ước tính 22.410.560 đ, và **tự duyệt luôn** (mỗi dòng ghi "Duyệt x/x") — nhập không đi qua
cửa duyệt thứ hai như phiếu mua hàng.

Tab "Phiếu từ yêu cầu" → nút **Lập phiếu**. Ô "Kho (nhập về)" chỉ chọn được **một kho cho cả phiếu**
mà 4 món thuộc 3 kho khác nhau ⇒ phải chẻ làm **3 phiếu nhập**, mỗi phiếu để SL nhập của các dòng
không thuộc kho đó bằng 0:

| Phiếu | Kho | Dòng nhập | Tiến độ YC sau khi ghi sổ |
|---|---|---|---|
| 1 | Kho Giấy (KHO-0002) | C300 512,06 + C150 479,9 | 991,96 / 1.000,52 — Đã cấp một phần |
| 2 | Kho Mực & Hóa chất (KHO-0003) | Keo gáy nhiệt PUR 4,09 | 996,05 / 1.000,52 — Đã cấp một phần |
| 3 | Kho Vật tư đóng gói (KHO-0004) | Màng BOPP cán mờ 4,47 | 1.000,52 / 1.000,52 — **Hoàn tất** |

Mỗi phiếu bấm "Tạo & Ghi sổ" → hộp xác nhận *"Tồn kho sẽ cộng ngay và phiếu không sửa được nữa"*
→ "Ghi sổ". Sau phiếu 1, cột TỒN KHO trong drawer đổi ngay: C300 500 → **1.012,06 kg**,
C150 800 → **1.279,9 kg**.

**Bước 6 — Kế hoạch vật tư.** Bộ lọc: **Cần mua ngay 0 · Đã đủ 100% 15/15**. Bốn dòng đỏ cũ đã tắt:

| Mặt hàng | Tồn / Cần | Độ phủ |
|---|---|---|
| Giấy C150 | 1.279,9 / 1.279,89 kg | 100% |
| Giấy C300 | 1.012,06 / 1.012,06 kg | 100% |
| Keo gáy nhiệt PUR | 4,09 / 4,08 kg | 100% |
| Màng BOPP cán mờ | 4,47 / 4,47 kg | 100% |

**Bước 7 — giữ chỗ.** Tab "Theo lệnh sản xuất": **Giữ đủ 7 · Đang giữ dở 0 · Chưa giữ 0**.
Bốn lệnh trước bị kẹt đã tự lấp đầy khi hàng về (Live Sync), **không phải bấm lại Giữ chỗ**:

| Lệnh | Trước | Sau |
|---|---|---|
| `LSX26-0003` | 0/1 (Chờ bù tồn) | **1/1** |
| `LSX26-0005` | 7/8 | **8/8** |
| `LSX26-0006` | 10/11 | **11/11** |
| `LSX26-0010` | 6/8 | **8/8** |
| `GB26-0001` · `LSX26-0007` · `LSX26-0009` | đã đủ | giữ nguyên đủ |

### Task 17 — xác minh cửa Sẵn sàng (XONG, DỪNG trước phát hành)

Kế hoạch sản xuất → tab "Lệnh sản xuất": **Tất cả 8 · Nháp 2 · Sẵn sàng 6**, cột VƯỚNG của cả 6
lệnh Sẵn sàng là "—". Mở từng lệnh, băng trạng thái đều ghi **"Không vướng gì" + "Sẵn sàng lập kế
hoạch"**: `LSX26-0003`, `0005`, `0006`, `0007`, `0009`, `0010`. Chip "Chưa giữ chỗ vật tư" đã biến
mất khỏi cả 6. **Không bấm nút phát hành nào** — dừng đúng theo yêu cầu.

**Chẩn đoán 2 lệnh còn Nháp (`LSX26-0004`, `LSX26-0008`).** Không phải thiếu vật tư. Băng cảnh báo
mở ra ghi đúng một dòng: *"Chưa khai Số trang / Trang mỗi tay — có công đoạn đổi tay sách → cái"*,
tức mã `thieu_trang_moi_tay` ở `lsx_service._thieu_cua`. Gốc rễ: hai lệnh này **không có phiếu thành
phần đi kèm** — băng đầu trang không có chip `PTG-…` (so với `LSX26-0010` có `PTG-2026-0003`), và
khối "Thành phẩm" trong tab Quy cách để trống hết (TÊN SẢN PHẨM —, LOẠI SẢN PHẨM —, ĐƠN VỊ TÍNH —),
nên **màn lệnh không hiện ô Số trang / Trang mỗi tay để mà nhập**. `LSX26-0010` có ô đó với giá trị
192 / 32. ⇒ Qua UI hiện tại không có đường mở khoá; giữ nguyên 2 lệnh ở Nháp.

**Lỗi ghi nhận thêm ở cửa sổ này**
- Ô "Vật tư" trong yêu cầu nhập kho **không khớp khi gõ có dấu tổ hợp**: gõ "Giấy C150" ra
  "Không có trong danh mục", trong khi đặt cùng chuỗi đó bằng API form của trình duyệt lại khớp
  ngay ⇒ hàm tìm không chuẩn hoá Unicode (NFC/NFD). Cùng họ với lỗi "BOPP cán mờ" đã ghi ở Task 16.
- Ô đó cũng **không tìm theo mã và không tìm theo chuỗi con**: "C300" báo không có trong danh mục,
  phải gõ từ đầu tên ("Giấy") mới ra danh sách.
- Ở khung hẹp (~490px), thanh tab con của module Kho ("Yêu cầu" / "Phiếu từ yêu cầu") **nằm lọt
  dưới thanh header chung** nên bấm không tới; phải cuộn nội dung lên hết mới bấm được.

### Task 18 (bổ sung 5/9/2026) — nối bìa ↔ ruột ở bước "Vào bìa keo nhiệt"

**Lỗi nhập liệu tự phát hiện khi bị hỏi lại:** ba cặp sách được dựng thành hai LSX rời nhưng chuỗi
phụ thuộc chỉ chạy trong nội bộ từng lệnh, không có cạnh nào nối lệnh Bìa sang bước "Vào bìa keo
nhiệt" của lệnh Ruột. Trên đồ thị, bìa và ruột là hai nhánh song song không gặp nhau — sai nghiệp
vụ (vào bìa ăn bìa đã cắt xong) và làm mù cả xếp lịch lẫn gom cụm bài ghép.

Hệ **có sẵn** chức năng này, đã ghi nhận ở nhật ký Task 11 mà không dùng: `lsx_cong_doan_phu_thuoc`
không ràng buộc hai đầu cùng lệnh, `san_xuat_repo._cross_lsx_edges_all` lọc riêng cạnh khác lệnh,
docstring `bai_ghep_graph.py` viết thẳng *"Sách = bìa (một lệnh) + ruột (một lệnh) nối nhau ở bước
vào bìa"*, và tab Phụ thuộc của drawer bước gom chip theo từng LSX của cả đơn (`nhomPhuThuoc`).

Đã bổ sung **3 cạnh chéo lệnh**, mỗi cạnh là `Cắt thành phẩm` (bước 60, bước cuối lệnh Bìa) →
`Vào bìa keo nhiệt` (bước 70 lệnh Ruột):

| Đơn | Lệnh Bìa (nguồn) | Lệnh Ruột (đích) | Trạng thái lúc sửa |
|---|---|---|---|
| DH005 | LSX26-0003 · bước 60 | LSX26-0004 · bước 70 | Nháp — sửa thẳng |
| DH003 | LSX26-0007 · bước 60 | LSX26-0008 · bước 70 | Nháp — sửa thẳng |
| DH006 | LSX26-0009 · bước 60 | LSX26-0010 · bước 70 | Sẵn sàng + **đang giữ chỗ** — phải nhả chỗ rồi giữ lại |

Thao tác từng lệnh: mở lệnh → tab **Công đoạn** → **Bảng danh sách** → bấm hàng #70 mở drawer →
tab **Phụ thuộc** → tick chip cuối trong nhóm lệnh Bìa → **Xong** → **Lưu công đoạn**. Sau khi lưu,
cột "Tiền nhiệm" của hàng 70 đọc **`Bắt tay` + `Bước LSX khác`**.

**Chặn gặp ở LSX26-0010:** bấm Lưu lần đầu bị từ chối, băng đỏ ghi *"Lệnh LSX26-0010 đang giữ chỗ
vật tư — nhả chỗ ở màn Kế hoạch vật tư trước khi sửa số lượng, quy cách, routing hoặc xoá lệnh."*
Đã đi đúng đường hệ chỉ: Kế hoạch vật tư → Theo lệnh sản xuất → **Nhả chỗ** (hộp xác nhận liệt kê
8 món trả về kho, kèm cảnh báo *"bật lại vẫn không chắc giữ lại được"*) → sửa routing → **Giữ chỗ**
lại. Sau khi giữ lại: bộ đếm về **Giữ đủ 7 · Đang giữ dở 0 · Chưa giữ 0**, dòng LSX26-0010 đọc
**100% (8/8 món)**, cửa xếp lịch về "Mở khóa". Trong khoảng nhả–giữ, hộp thoại xác nhận không có
lệnh nào khác thiếu 8 món này nên không ai cướp chỗ.

**Hai lỗi giao diện gặp lúc làm:**
- Chip trong tab Phụ thuộc của các lệnh cũ hiện trơ chữ **"Công đoạn"** thay vì tên bước (bug
  `lsx_cong_doan.ten` đã ghi ở Task 11); LSX26-0009/0010 thì hiện đúng tên. Với lệnh hiện chữ trơ,
  chỉ còn cách dựa vào **thứ tự chip = thứ tự bước** để chọn.
- Chip cuối của nhóm dưới cùng bị **thanh chân drawer che khuất một nửa**; bấm vào phần bị che
  không ăn, phải cuộn thân drawer xuống rồi mới tick được.

**Còn nợ:** hai lệnh Ruột `LSX26-0004`/`LSX26-0008` vẫn ở Nháp vì `thieu_trang_moi_tay` (không có
phiếu thành phần nên màn lệnh không hiện ô Số trang / Trang mỗi tay). Và bước "Vào bìa" mới chỉ khai
keo PUR, chưa có dòng nào biểu diễn "ăn 2.000 tấm bìa từ lệnh kia" — chưa rõ hệ có mô hình bán thành
phẩm chéo lệnh hay không, cần bàn riêng.

---

## Task 19 — Vá lỗi nhãn bước trơ chữ "Công đoạn" (05/09/2026)

Chủ hỏi *"sao để công đoạn hết trơn vậy, bộ nó không có tên à"* rồi ra lệnh *"sửa luôn cả 3 đi"*.
Đây là lần đầu trong phiên đụng CODE (từ Task 1 tới 18 chỉ thao tác UI).

### Chuỗi nhân quả

1. `toBody` ở FE gửi `ten: r.ten || "Công đoạn"`. Bước chèn tay để trống ô tên tự do ⇒ client tự
   điền chuỗi tạm.
2. `replace_routing` có sẵn đường lùi `ten = ten or cd_obj.ten` (lấy tên công đoạn đang gắn) nhưng
   chuỗi tạm KHÔNG rỗng nên nhánh đó không bao giờ chạy; `row.ten = ten or "Công đoạn"` ghi thẳng
   chuỗi tạm vào cột. Chọn công đoạn về sau chỉ set `cong_doan_id`, không đồng bộ lại `ten`.
3. Nguồn đẩy dữ liệu hỏng vào: `doiCongDoan` gọi `GET /api/lsx/{id}/mac-dinh-buoc/{cd}`; endpoint
   này đang 500 (chip `task_ae9163e6`), nhánh `catch` giữ nguyên `tenHienTai` — tức nhãn tạm.
4. Ba bề mặt hiện SAI vì đọc thẳng cột `ten`, không tra qua `cong_doan_id`:
   `bai_ghep_service._node()` (sơ đồ bài ghép), `phu_thuoc_options` (chip Phụ thuộc + panel
   "Bước LSX khác"). Bảng routing và thẻ DAG của lệnh thì ĐÚNG vì đi qua `tenBuoc()`.

### Đã sửa

| # | Chỗ | Việc |
|---|---|---|
| 1 | `frontend/src/pages/lsxBuoc.ts:328` | `toBody` gửi `ten: r.ten.trim()`, bỏ literal |
| 2 | `backend/app/services/lsx_service.py` (`replace_routing`) | Bước đã gắn công đoạn mà `ten` == nhãn tạm ⇒ coi như trống, lấy tên danh mục. Hằng `TEN_BUOC_TRONG` khai ở `models/lsx.py` |
| 3 | `backend/app/services/lsx_service.py` (`phu_thuoc_options`) | Trả tên công đoạn trước, `step.ten` sau — khớp luật của `tenBuoc()` bên FE |
| 4 | `backend/app/db_migrations.py` mg `0267_ten_buoc_tro_cong_doan` | Nắn ngược `lsx_cong_doan.ten` + `bai_ghep_cong_doan.ten` cho dòng đã có `cong_doan_id`. Đây là cái chữa sơ đồ bài ghép |
| 5 | `frontend/src/pages/LsxRoutingTable.tsx` (`doiCongDoan`) | Nhánh `catch` lấy tên từ `congDoanRefs` thay vì giữ tên cũ |

**Bẫy gặp khi viết migration:** bản đầu gọi `_existing_columns()` GIỮA vòng lặp hai bảng. Trên
SQLite in-memory `inspect()` mượn đúng connection của Session nên lần soi thứ hai rollback mất
UPDATE của bảng thứ nhất — đúng bẫy đã ghi chú ở mg `0265`. Test bắt được, đã hoisted phép soi ra
trước vòng lặp. Giữ lại thành `backend/tests/test_migration_0267_ten_buoc.py`.

### Xác minh

- `npx tsc --noEmit` exit 0.
- vitest `lsxBuoc.test.ts` + `BuocChungForm.test.tsx`: 10/10.
- pytest `test_lsx_service` + `test_bai_ghep_service` + `test_giu_cho_vat_tu`: **213 passed**.
- pytest `test_migration_0267_ten_buoc.py`: 2/2 (nắn đúng, KHÔNG đè tên tự do người đặt, idempotent).
- Backend restart trỏ `svn_erp_trong` (đặt `SEED_DEMO=false` để seeder không đè routing nhập tay),
  startup sạch, mg `0267` ghi vào `schema_migrations` lúc 07:01:01.
- Đọc thẳng DB `svn_erp_trong` (script CHỈ ĐỌC ngoài `backend/`): **0 dòng** còn nhãn tạm ở cả
  `lsx_cong_doan` lẫn `bai_ghep_cong_doan`; toàn bộ 6 bước LSX26-0009 và 10 bước LSX26-0010 khớp
  đúng tên danh mục.

### Nghiệm thu bằng UI thật (chủ tự đăng nhập, trợ lý thao tác chuột)

Đường bấm: hamburger → **Bài ghép** → tab **Bài ghép đã tạo** → dòng **GB26-0001** → tab
**Công đoạn**. Ba thẻ chủ khoanh đỏ nay đọc **#10 Bình bài & dàn trang · #20 Ghi kẽm CTP ·
#30 In proof duyệt màu** trên CẢ hai hàng LSX26-0003 và LSX26-0009. Cuộn ngang canvas: **#50 cán
màng mờ · #60 Cắt thành phẩm** cũng hết trơ (trước đó hàng LSX26-0003 hiện "Công đoạn" ở cả #50/#60).

Đường bấm tiếp: hamburger → **Kế hoạch sản xuất** → tab **Lệnh sản xuất 8** → dòng **LSX26-0010** →
tab **Công đoạn**. Node bóng mờ đầu chuỗi đọc **"LSX26-0009 · Cắt thành phẩm"** kèm câu "Lệnh này
chỉ chạy sau khi bước trên của lệnh kia xong" — cạnh chéo lệnh Task 18 còn nguyên. Bấm bút chì trên
thẻ **#10** → drawer **BƯỚC 01/10 · Tổ · Bình bài & dàn trang** → tab **Phụ thuộc**: cả 16 chip của
hai nhóm `LSX26-0010 · hiện tại` và `LSX26-0009` đều mang tên thật, KHÔNG còn chip nào ghi
"Công đoạn". Bấm **Xong**, nút "Lưu công đoạn" vẫn `disabled` ⇒ chỉ xem, không sửa gì.

Bộ đếm danh sách lệnh giữ nguyên **Tất cả 8 · Nháp 2 · Sẵn sàng 6**; LSX26-0010 vẫn "Sẵn sàng ·
Không vướng gì · 8 món vật tư".

---

## Task 20 — Lỗi 500 ở `GET /api/lsx/{id}/mac-dinh-buoc/{cd}` (05/09/2026)

Đây là NGUỒN đẻ ra đám dữ liệu trơ chữ "Công đoạn" ở Task 19: `doiCongDoan` gọi endpoint này, gặp
500 thì nhánh `catch` giữ nguyên tên cũ.

**Nguyên nhân:** schema trả về `BuocMacDinhOut` khai `loai_buoc: str` BẮT BUỘC, còn
`lsx_service.mac_dinh_buoc()` cố ý KHÔNG trả trường đó (loại Máy/Tổ/Thuê ngoài thuộc bước KHSX,
đổi công đoạn không được ghi đè). Router `lsx.py:514` gọi `model_validate` trên dict thiếu trường
⇒ `ValidationError` ⇒ 500 **mọi lần gọi**, không phải lúc được lúc không. Traceback nguyên văn nằm
ở `backend/uv8000.log`.

**Vì sao bộ test không bắt được:** cả ba test của endpoint gọi THẲNG service
(`lsx_svc.mac_dinh_buoc(...)`), không đi qua router, nên `BuocMacDinhOut` chưa từng chạy trong
suite. Tréo ngoe là `test_lsx_service.py:2618` còn khẳng định
`{"loai_buoc", "may_id", "nang_suat", "don_vi_nang_suat"}.isdisjoint(m)` — test chốt "service không
trả", schema chốt "bắt buộc phải có", hai bên khoá ngược nhau mà không ai đứng giữa.

Mặt trái của bẫy `pydantic-nuot-field-im-lang`: thừa field so với schema thì bị nuốt im lặng,
thiếu field bắt buộc thì 500 thẳng.

**Đã sửa:**
- `backend/app/schemas/lsx.py` — gỡ `loai_buoc` và 6 trường chết khác (`may_id`, `nang_suat`,
  `don_vi_nang_suat`, `so_nhan_cong`, `so_nhan_cong_tieu_chuan`, `so_nhan_cong_toi_da`) khỏi
  `BuocMacDinhOut`; ghi rõ trong docstring vì sao KHÔNG được khai lại. Type `LsxBuocMacDinh` bên FE
  vốn đã không có mấy trường này — chỉ schema backend bị bỏ quên.
- `backend/tests/test_lsx_service.py` — thêm `BuocMacDinhOut.model_validate(m)` vào
  `test_mac_dinh_buoc_chi_tra_thuoc_tinh_cua_cong_doan`, tức chạy đúng chặng cuối của router.

**Chu trình TDD đã chạy:** thêm assert → ĐỎ đúng `ValidationError: loai_buoc Field required` (khớp
từng chữ với traceback production) → gỡ trường khỏi schema → XANH. Rồi
`pytest tests/test_lsx_service.py tests/test_khsx_ui_contract.py` = **121 passed**.

Backend restart (`Win32_Process.Create`, giữ `DATABASE_URL` trỏ `svn_erp_trong` + `SEED_DEMO=false`),
`/api/health` 200 sau 8s, log khởi động sạch.

**Nghiệm thu bằng UI thật (đã trả xong nợ, 05/09/2026 — chủ tự đăng nhập):**

Đường bấm: hamburger → **Kế hoạch sản xuất** → tab **Lệnh sản xuất 8** → hàng **LSX26-0010** →
tab **Công đoạn** → nút **Bảng danh sách** → bấm hàng **#10 Bình bài & dàn trang** (mở drawer
"BƯỚC 01/10 · Tổ") → bấm nhãn **TÊN CÔNG ĐOẠN** để đưa focus vào ô select → đổi select sang
**In proof duyệt màu** → đổi ngược lại **Bình bài & dàn trang** → **Đóng panel** → **Làm mới**.

Thấy gì:

- `backend/uv8000.log`: `GET /api/lsx/10/mac-dinh-buoc/55` → **200 OK** và
  `GET /api/lsx/10/mac-dinh-buoc/53` → **200 OK**. Trước khi sửa schema, đúng hai lệnh này 500.
- Vùng `aria-live` của bảng routing bắt được đúng câu của nhánh THÀNH CÔNG:
  *"Đã đổi sang Bình bài & dàn trang và lấy lại đơn vị, tổ phụ trách"*, rồi ngay sau là
  *"Đã nạp 1 đầu việc khoán"*. Câu thứ hai là của `napDauViec`, chỉ được gọi trong `try` —
  nhánh `catch` không gọi, nên hai câu liên tiếp là bằng chứng phân biệt sạch.
- Hàng #10 đổi đơn vị theo công đoạn mới (`bài in → bản proof` rồi về `bài in`), tổ vẫn giữ
  **Tổ kỹ thuật** (nhánh `catch` sẽ đặt `department_id: null`), và băng
  *"Bước này không nằm trên dòng giấy (đếm bằng bản proof)"* hiện lên — cả ba đều lấy từ payload
  của chính endpoint vừa hết 500.
- Không bấm **Lưu công đoạn**; log không có `PUT /api/lsx/*/routing`. Sau **Làm mới**, nút
  **Lưu công đoạn** trở lại `disabled` và sơ đồ DAG vẫn `#10 Bình bài & dàn trang` — DB không bị đụng.
- Cả 10 nút bước trên DAG hiện tên danh mục thật, không còn nhãn `Công đoạn` nào (kiểm bằng
  đếm chuỗi `#<số>
Công đoạn` trong `main` = 0) — Task 19 vẫn đứng.

**Có tắt qua công cụ ở một chỗ, nói rõ:** ô công đoạn là `<select>` gốc của trình duyệt. Bấm chuột
vào nó mở popup của Chrome — popup đó không nằm trong DOM nên phím mũi tên gửi qua CDP rơi vào
khoảng không (đã thử: `selectedIndex` không nhúc nhích, `Escape` còn đóng luôn drawer). Vì vậy giá
trị select được đặt bằng `form_input` của khung Browser — vẫn là thao tác trên chính control đó,
bắn `input`/`change` thật lên React, không phải gọi API thay bước. Mọi bước còn lại đều bấm chuột
theo toạ độ thật.

**Phát hiện kèm (chưa sửa, chỉ ghi):** hai lần đổi công đoạn kéo theo
`POST /api/lsx/10/xem-truoc-routing` → **409 Conflict**. Nguyên nhân: `LSX26-0010` có
`giu_cho_bat = true`, mà `_chan_dang_giu_cho` cố ý chặn CẢ preview (docstring nói rõ: cho preview
chạy qua thì màn nói dối). FE `xemTruocChuoi` nuốt lỗi im lặng nên người dùng không biết bản xem
trước đã chết, và bấm Lưu mới ăn 409. Đây là hành vi có sẵn, không phải hồi quy của bản vá này.

### Task 21 — 409 im lặng của bản xem-trước routing

**Triệu chứng.** Mỗi lần đổi công đoạn trên `LSX26-0010`, ngoài `mac-dinh-buoc` (200 sau Task 20)
còn có `POST /api/lsx/10/xem-truoc-routing` → **409 Conflict**. Trên màn không có dấu vết nào.

**Nguyên nhân.** `LsxService._chan_dang_giu_cho` chặn khi `lsx.giu_cho_bat = true`, và docstring của
nó nói rõ là **cố ý chặn CẢ preview**: cho preview chạy qua thì màn nói dối, bấm Lưu thật mới báo
lỗi. `xem_truoc_routing` chạy đúng đường `replace_routing(commit=False)` nên dính guard này.
`LSX26-0010` đang giữ chỗ (6/8 lệnh trong `svn_erp_trong` đều bật cờ — Task 15 bật, có chủ ý).

Ba tầng cộng lại thành lỗi:

1. Server khoá routing nhưng **không nói ra cho client** — `LsxOut` không có `giu_cho_bat`.
2. FE do đó vẫn mở bảng routing cho sửa, nút **Lưu công đoạn** vẫn sáng.
3. `xemTruocChuoi` có `catch {}` **rỗng**, kèm câu trấn an SAI trong comment ("bấm Lưu công đoạn
   server vẫn tính đúng" — không, Lưu cũng 409). Nhánh `catch` của `doiCongDoan` cũng nuốt y hệt.

Kết quả: người kế hoạch sửa xong cả routing, số vào–ra đứng im không ai giải thích, tới lúc bấm Lưu
mới hiện băng đỏ — đúng chặng đã ghi ở Task 18. Đây cũng chính là cơ chế đẻ ra dữ liệu trơ nhãn
"Công đoạn" ở Task 19: `mac-dinh-buoc` 500, `catch` nuốt, bước đổi được mỗi cái tên.

**KHÔNG nới guard ở backend.** Docstring đã cân nhắc và bác đúng phương án đó; sửa nó là lật một
quyết định có chủ ý của chủ. Chỗ sai là màn hình giấu cái khoá, nên vá ở đó.

**Đã sửa (5 chỗ):**

| Tầng | File | Việc |
|---|---|---|
| Schema | `backend/app/schemas/lsx.py` | `LsxOut` thêm `giu_cho_bat: bool = False` |
| Type | `frontend/src/api/client.ts` | `LsxDetail.giu_cho_bat: boolean` |
| Cha | `frontend/src/pages/LsxDetailView.tsx` | `giuCho={d.giu_cho_bat}` |
| Bảng | `frontend/src/pages/LsxRoutingTable.tsx` | `suaDuoc = canUpdate && !giuCho` gác 8 cửa ghi · băng khoá hổ phách kèm đường lùi · dòng phụ đổi thành "chỉ xem" · băng đỏ `loiDoiCd` cho CẢ hai nhánh từng nuốt lỗi |
| CSS | `frontend/src/pages/ke-hoach-sx.css` | `.khsx-ghep-bang--khoa` / `--loi` |

`suaDuoc` tách khỏi `canUpdate` để giữ LÝ DO: hết quyền thì im lặng ẩn nút, còn giữ chỗ thì phải nói
ra. Băng khoá xét `canUpdate && giuCho` chứ không xét `suaDuoc` — dùng `suaDuoc` là băng không bao
giờ hiện.

**TDD.** `test_chi_tiet_lenh_noi_ra_dang_giu_cho_vat_tu` → ĐỎ đúng
`AttributeError: 'LsxOut' object has no attribute 'giu_cho_bat'` (bẫy pydantic-nuốt-field lần thứ
hai trong hai task liền) → thêm field → XANH. Thêm 2 test hợp đồng UI trong
`test_khsx_ui_contract.py` (mọi cửa ghi phải qua `suaDuoc`; hai nhánh catch phải gọi `setLoiDoiCd`).
`pytest tests/test_lsx_service.py tests/test_khsx_ui_contract.py` = **124 passed**;
`npx tsc --noEmit` sạch; vitest **348 passed / 37 file**.

**Nghiệm thu bằng UI thật.** Restart uvicorn (`Win32_Process.Create`, `svn_erp_trong`,
`SEED_DEMO=false`), `/api/health` 200 sau 3s.

*Nhánh KHOÁ — LSX26-0010:* Kế hoạch sản xuất → Lệnh sản xuất 8 → hàng LSX26-0010 → tab Công đoạn.
Thấy băng hổ phách *"Lệnh đang giữ chỗ vật tư nên công đoạn khoá lại… Vào Kế hoạch vật tư › Theo
lệnh sản xuất bấm Nhả chỗ, sửa công đoạn xong rồi Giữ chỗ lại."*; dòng phụ đọc *"kế thừa từ bài tính
giá · chỉ xem"*; **0 nút "Lưu công đoạn"**. Sang Bảng danh sách: cả 10 hàng `draggable=false`, 0 nút
thao tác/hàng. Mở drawer bước #10: ô TÊN CÔNG ĐOẠN `disabled`, 3/3 ô nhập của tab khoá. Log: **không
có** `mac-dinh-buoc`, `xem-truoc-routing`, 409 hay 500 nào.

*Nhánh MỞ — LSX26-0008 (không giữ chỗ):* không băng, dòng phụ *"sửa được tại lệnh này"*, 2 nút Lưu
(disabled vì chưa dirty), hàng kéo được, 4 nút/hàng. Đổi công đoạn bước #10 sang **In proof duyệt
màu** → `GET /api/lsx/8/mac-dinh-buoc/55` **200** và `POST /api/lsx/8/xem-truoc-routing` **200**
(không còn 409), vùng `aria-live` bắt được *"Đã đổi sang In proof duyệt màu và lấy lại đơn vị, tổ
phụ trách"* rồi *"Đã nạp 1 đầu việc khoán"*, hàng đổi đơn vị sang `bản proof`, không băng đỏ.

*Băng đỏ:* dựng lỗi THẬT bằng cách tắt uvicorn rồi đổi công đoạn ở LSX26-0008 → hiện đúng
*"Chưa lấy được mặc định của công đoạn: Cannot reach the server… — bước mới chỉ đổi được TÊN, đơn vị
và tổ phụ trách chưa lấy lại."*, và hàng bày đúng cái nó cảnh báo: tên đổi thành "In proof duyệt
màu" nhưng đơn vị vẫn `bài in` và tổ thành *"tổ mặc định / chưa gán tổ"*. Trước bản vá, y hệt tình
huống này chạy **câm** — đúng cách dữ liệu Task 19 hỏng.

Bật lại uvicorn → **Làm mới** → bước #10 về `Bình bài & dàn trang · Tổ kỹ thuật`, băng đỏ tắt, hai
nút Lưu `disabled`. Rà log cả lượt: **không có PUT/POST ghi nào, không 409, không 500** — DB không
bị đụng.

**Tắt qua công cụ một chỗ (nói rõ):** ô công đoạn là `<select>` gốc; bấm chuột mở popup của Chrome
nằm ngoài DOM nên phím gửi qua CDP rơi vào khoảng không (đã thử, `selectedIndex` không đổi). Giá trị
select đặt bằng `form_input` của khung Browser — vẫn tác động lên chính control đó và bắn
`input`/`change` thật lên React. Mọi bước khác bấm chuột theo toạ độ thật.

**Còn để lại (chưa sửa, không thuộc phạm vi câu hỏi):** `LsxService.update` cũng chặn giữ chỗ khi
đổi `so_luong_dat`/`quy_cach`, và `xoa` cũng vậy. Hai đường đó BÁO ĐƯỢC lỗi (băng `BangLoi` của
`LsxDetailView`) nên không câm như routing, nhưng vẫn để người dùng gõ xong mới biết. Muốn dọn nốt
thì dùng đúng cờ `giu_cho_bat` vừa mở đường ra.


---

## Task 22 — Nốt hai đường còn lại của khoá giữ chỗ: sửa quy cách và xoá lệnh

**Triệu chứng.** Cùng gốc với Task 21, nhẹ hơn một bậc. Lệnh đang giữ chỗ vật tư: người kế hoạch mở
tab **Quy cách** gõ lại khổ giấy / số trang / bình bài — mọi ô đều sáng, nhãn khối còn ghi *"thông
số — sửa được"* — gõ xong bấm **Lưu thay đổi** mới ăn 409 *"Lệnh LSX26-00xx đang giữ chỗ vật tư…"*.
Nút **Xoá lệnh** y hệt: sáng, bấm ra hộp xác nhận nói *"Lệnh chưa phát hành nên xoá được"* (sai),
bấm Xoá mới 409.

**Nguyên nhân.** `_chan_dang_giu_cho` gác ba đường ghi vào lượng vật tư: `update` khi
`so_luong_dat` ĐỔI hoặc payload có `quy_cach`, `replace_routing`, và `xoa`. Task 21 đã đưa cờ
`giu_cho_bat` ra tới client và dọn đường routing; hai đường còn lại vẫn dựng màn theo `canUpdate`
nên chỉ biết "có quyền hay không", không biết "server đang khoá".

**Quyết định giữ nguyên backend.** Ranh giới của guard là đúng và FE bám theo ĐÚNG ranh giới đó:
tên lệnh / hạn / ghi chú / cờ gấp không đụng vật tư nên vẫn lưu được. Không nới cũng không siết
backend trong task này.

**Sửa (chỉ FE + test).**

| Chỗ | Trước | Sau |
|---|---|---|
| `LsxDetailView` | không biết cờ | `const giuCho = !!d?.giu_cho_bat` · `const suaQc = canUpdate && !giuCho` |
| 13 ô nhập tab Quy cách | `disabled={!canUpdate}` | `disabled={!suaQc}` — khoá thì `qcDoi` đứng false ⇒ `luu()` không gửi `quy_cach` ⇒ nút Lưu vẫn dùng được cho tên/hạn/ghi chú |
| Nhãn khối Giấy & tờ | chết cứng *"thông số — sửa được"* | `{suaQc ? "sửa được" : "chỉ xem"}` — không thì màn tự cãi nhau với băng khoá ngay trên |
| Đầu tab Quy cách | không có gì | băng `khsx-ghep-bang--khoa` nói lý do + đường lùi + **cái gì vẫn lưu được** |
| Nút **Xoá lệnh** | luôn sáng | thay bằng chip `khsx-khoa-chip` *"Giữ chỗ vật tư — chưa xoá được"* (title chỉ đường nhả chỗ) |

Chip chứ không phải `<button disabled>`: nút mờ chỉ có tooltip, người dùng bấm không ăn rồi tự đoán
là mình hết quyền. Chip nằm ở đầu màn nên tab nào cũng thấy — đó cũng là chỗ báo khoá cho ai đang
đứng ngoài tab Quy cách.

**TDD.** 3 test mới. `test_giu_cho_chan_dung_ba_duong_con_ten_ghi_chu_van_luu_duoc` chốt HÀNH VI
server (chặn `so_luong_dat` đổi / `quy_cach` / `xoa`; cho qua tên+ghi chú+gấp; cho qua khi gửi lại
đúng số cũ — `luu()` của FE gửi kèm `so_luong_dat` mỗi lần lưu, chặn chỗ này là nút Lưu thành nút
báo lỗi). Hai test hợp đồng UI chốt CẤU TRÚC màn. Bẫy gặp phải: `update` GÁN field rồi mới gọi
`_chan_dang_giu_cho`, nên trong CÙNG một session, lần nổ để lại số bẩn trong identity map và lần gọi
sau so với số bẩn — test phải `db.rollback()` sau mỗi lần chặn (thật thì mỗi request một session).
Đỏ trước khi sửa: bản HEAD có 13 lần `disabled={!canUpdate}` và 0 lần `khsx-khoa-chip`.
`pytest tests/test_lsx_service.py tests/test_khsx_ui_contract.py` = **127 passed**;
`npx tsc --noEmit` sạch; vitest **348 passed / 37 file**.

**Nghiệm thu bằng UI thật.** Không restart BE (không đổi dòng nào ở backend ngoài test); `/api/health`
200, FE 5173 200.

*Nhánh MỞ — LSX26-0008:* tab **Quy cách** → không băng khoá, **0/11 ô khoá**, nút **Xoá lệnh** có
mặt. Bấm ba lần vào ô **Bleed (mm)** rồi gõ `3` → ô nhận `3`, hiện cặp nút **Hoàn tác / Lưu thay
đổi**, `POST /api/lsx/8/xem-truoc-quy-cach` **200**. Bấm **Hoàn tác** → Bleed về `0`, cặp nút biến
mất. Không lưu.

*Nhánh KHOÁ — LSX26-0010:* Quay lại danh sách lệnh → **Mở lệnh LSX26-0010** → tab **Quy cách**. Băng
hổ phách đọc đúng *"Lệnh đang giữ chỗ vật tư nên thông số quy cách khoá lại — mọi số ở đây đều đổi
lượng vật tư cần, mà phần đã giữ chỗ không hay biết. Vào Kế hoạch vật tư › Theo lệnh sản xuất bấm
Nhả chỗ, sửa xong rồi Giữ chỗ lại. Tên lệnh, hạn, ghi chú và cờ gấp vẫn sửa và lưu được bình
thường."*; nhãn khối *"thông số — chỉ xem"*; **13/13 ô khoá**. Bấm ba lần vào **Khổ giấy nguyên dài**
rồi gõ `999` → ô vẫn `650`, focus không vào được ô (đứng ở `SECTION`), **không** hiện nút Lưu.

*Chip xoá:* lệnh đang **Sẵn sàng** nên cả nút Xoá lẫn chip đều không render (đúng điều kiện
`trang_thai !== "san_sang"`). Bấm **Mở lại để sửa** → trạng thái **Nháp** → chỗ nút Xoá hiện chip hổ
phách viền đứt *"Giữ chỗ vật tư — chưa xoá được"*, `title` = *"Nhả chỗ ở Kế hoạch vật tư › Theo lệnh
sản xuất rồi mới xoá được lệnh."*, và **0 nút "Xoá lệnh"**. Bấm **Sẵn sàng lập kế hoạch** trả lệnh về
**Sẵn sàng** — dữ liệu về đúng chỗ cũ.

*Log:* từ mốc `/api/health` của lượt này tới cuối, 145 dòng, **không có 409, không có 500**, request
ghi duy nhất là 2 lần `POST /api/lsx/10/trang-thai` 200 (mở lại + đóng về Sẵn sàng, tự dựng rồi tự
trả). Không PUT/DELETE nào.

**Không tắt qua công cụ nào ở task này** — mọi bước bấm chuột/gõ phím thật; `find`/`scroll_to` chỉ
dùng để cuộn phần tử vào tầm nhìn trước khi bấm theo toạ độ.

**Ghi nhận bên lề.** (1) `LsxService.update` KHÔNG chặn `so_con` dù đổi số con/tờ là đổi số tờ kế
hoạch, tức đổi lượng giấy cần — FE khoá ô này theo cụm quy cách nên chặt hơn server một nấc. **Đã
sửa ở Task 23.** (2) LSX26-0010 lúc về Nháp hiện chip đỏ *"Chưa tính được nhu cầu vật tư của lệnh"* trong khi nó
đang GIỮ CHỖ vật tư — hai câu này đọc ngược nhau, cần soi riêng.

---

## Task 23 — `so_con` lọt khoá giữ chỗ

**Triệu chứng.** Lệnh đang giữ chỗ vật tư vẫn đổi được **số con/tờ** (ô *Bình bài*) qua
`PUT /api/lsx/{id}` mà server không kêu gì. Đo bằng số thật trên LSX26-0008: bình bài `16 → 8` làm
**Vào máy 368 → 505 tờ** và **Giấy nguyên 368 → 505 tờ** (+137 tờ giấy), công thợ 3.349.026 →
3.376.705 đ. Đúng loại thay đổi mà giữ chỗ phải biết, mà nó không biết.

**Nguyên nhân.** Điều kiện gọi guard hẹp hơn điều kiện tính lại chuỗi ngược ngay dưới nó:

```python
if ("so_luong_dat" in changed or data.get("quy_cach")):   # gác
    self._chan_dang_giu_cho(lsx)
...
if {"so_luong_dat", "so_con"} & set(changed) or data.get("quy_cach"):   # tính lại
    self._ap_chuoi_nguoc(lsx)
```

`so_con` nằm ở vế tính lại mà thiếu ở vế gác. Nó đọc như "thông số trình bày" nên lọt, nhưng bình
bài lại là số tờ kế hoạch khác đi, tức lượng giấy cần khác đi.

**Sửa.** `backend/app/services/lsx_service.py` — cho hai điều kiện TRÙNG KHÍT:
`if {"so_luong_dat", "so_con"} & set(changed) or data.get("quy_cach")`. Luật rút ra và ghi thành
comment tại chỗ: **cái gì làm `_ap_chuoi_nguoc` viết lại số tờ vào máy thì cái đó đổi lượng vật tư
cần ⇒ phải qua guard.** Kèm sửa docstring `_chan_dang_giu_cho` và câu lỗi 409 cho đủ vế
(*"…trước khi sửa số lượng, **số con/tờ**, quy cách, routing hoặc xoá lệnh."*).

FE **không đổi dòng nào**: Task 22 đã khoá ô *Bình bài* theo cụm `suaQc`, lúc đó chặt hơn server
một nấc — nay server bắt kịp, hai bên khớp.

**TDD.** Thêm một `pytest.raises` cho `so_con` vào
`test_giu_cho_chan_dung_ba_duong_con_ten_ghi_chu_van_luu_duoc` → ĐỎ đúng
`Failed: DID NOT RAISE <class 'LsxConflict'>` → sửa guard → XANH.
`pytest tests/test_lsx_service.py tests/test_khsx_ui_contract.py` = **127 passed**. Siết guard là
đổi hành vi server nên chạy thêm cả nhóm có đụng giữ chỗ / bài ghép:
`test_giu_cho_vat_tu · test_bai_ghep_service · test_bai_ghep_2_service · test_bai_ghep_2_api ·
test_san_xuat_release · test_san_xuat_release_update · test_lsx_tong_quan` = **154 passed**. Rà
người gọi: chỉ `routers/lsx.py:372` gọi `LsxService.update`; bài ghép dùng `so_con=` như tham số
tính toán chứ không đi qua `update`, nên không dính.

**Nghiệm thu bằng UI thật.** Restart uvicorn (`Win32_Process.Create`, `svn_erp_trong`,
`SEED_DEMO=false`) vì đổi service; `/api/health` 200.

*Nhánh KHOÁ — LSX26-0010:* tab Quy cách, ô **Bình bài** `disabled` (Task 22 đã khoá) ⇒ luật mới
KHÔNG có đường nào chạm tới từ giao diện. Đây cũng là lý do 409 của `so_con` không có ảnh chụp UI:
màn chặn trước, server chỉ là lưới cuối. Bằng chứng cho vế chặn là test ở trên.

*Nhánh MỞ — LSX26-0008 (không giữ chỗ, phải KHÔNG bị siết oan):* mốc đầu Bình bài `16`, Vào máy
`368 tờ`, Giấy nguyên `368 tờ`, Công thợ `3.349.026 đ`. Bấm ba lần vào ô **Bình bài**, gõ `8` → hiện
**Hoàn tác / Lưu thay đổi** → bấm **Lưu thay đổi** → `PUT /api/lsx/8` **200**, KPI nhảy sang
`8 cái · 505 tờ · 505 tờ · 3.376.705 đ`, không băng lỗi. Gõ lại `16` → **Lưu thay đổi** →
`PUT /api/lsx/8` **200**, KPI về đúng mốc đầu `16 cái · 368 tờ · 368 tờ · 3.349.026 đ`. Dữ liệu trả
nguyên trạng.

*Log:* từ mốc `Application startup complete` của lần restart tới cuối — **0 dòng 409, 0 dòng 500**;
request ghi vào LSX chỉ có đúng 2 lần `PUT /api/lsx/8` 200 nói trên.

**Còn để lại.** Hai plan doc cũ (`2026-08-30-ke-hoach-vat-tu.md:1660` và mục Task 21 ở trên) còn
trích câu lỗi 409 bản cũ. Đó là biên bản theo ngày nên không sửa ngược; nguồn sự thật là code.

## Task 24 — Ô "Giấy" ở lệnh chỉ mở tới giấy đang dùng + giấy thay thế của nó

**Yêu cầu.** *"Giấy ở đó chỉ chọn được giấy đó, với giấy thay thế của giấy đó thôi, còn lại không
cho chọn và nhập liệu đâu."*

**Ô "Giấy" ở lệnh là cái gì (chẩn đoán trước khi sửa).** Nó là **giấy chạy máy của lệnh**, cất ở
`lsx.quy_cach_json.giay_id`, KHÔNG phải một dòng trong bảng vật tư: LSX26-0008 có 7 dòng
`lsx_cong_doan_vat_tu` (4 mực offset, dung môi rửa máy, keo gáy PUR, băng keo) và **không có dòng
giấy nào** — giấy đi đường quy cách, số tờ do chuỗi ngược tính ra. Đổi ô này chỉ kéo theo `gsm` +
`giay_ten` (`ap_quy_cach`), **không kéo khổ**: danh mục giấy đã bỏ khổ (mọi dòng `kho_dai = kho_rong
= 0`, ghi chú model *"0 = cuộn/khổ mở"*, đơn giá tính **đ/kg**), nên hai ô *Khổ giấy nguyên* là số
gõ tay tại lệnh chứ không phải thuộc tính của loại giấy.

**Vì sao phải bó lại.** Đổi giấy tại lệnh là **chữa cháy khi hết hàng**, không phải chọn lại giấy từ
đầu. Mở cả danh mục là mời người kế hoạch đổi C150 ruột sách sang C300 bìa mà không ai chặn. Danh
mục đã có sẵn chỗ khai điều đó: `giay_nguyen.thay_the_ids` (*"Giấy khác dùng thay được món này khi
thiếu hàng. Chỉ để tra cứu, không tự suy chiều ngược lại."*).

**Sửa — chỉ FE, backend không đụng dòng nào.** `GiayRow` của `GET /api/vat-lieu-kho/giay` đã trả sẵn
`thay_the_ids`, nên `frontend/src/pages/LsxDetailView.tsx` chỉ cần nhận thêm trường đó vào `giayRefs`
rồi lọc:

```tsx
const giayNeoId = qc.giay_id == null ? null : Number(qc.giay_id);
const giayNeo = giayRefs?.find((g) => g.id === giayNeoId) ?? null;
const giayChonDuoc = !giayRefs ? null
  : giayNeoId == null ? giayRefs
  : giayRefs.filter((g) => g.id === giayNeoId || (giayNeo?.thayThe ?? []).includes(g.id));
```

Ba quyết định trong mấy dòng đó, đã ghi thành comment tại chỗ:

- **Neo vào giấy ĐÃ LƯU (`qc.giay_id`), không phải giấy đang chọn dở trong form.** Neo theo form thì
  mỗi lần đổi, danh sách mở ra theo thay-thế-của-thay-thế; nhảy vài nhịp là ra khỏi vùng đã duyệt.
- **Không suy ngược.** Quan hệ thay thế MỘT CHIỀU: C150 khai thay được bằng C100 không có nghĩa lệnh
  đang chạy C100 được đổi về C150.
- **Lệnh chưa có giấy (`giay_id` null) thì mở cả danh mục** — không có gì để neo, khoá lại là nhốt
  luôn, không bao giờ chọn được giấy đầu tiên. Cũng vì vậy option rỗng *"— chưa chọn giấy —"* chỉ
  hiện khi `giayNeoId == null`.

Tính thẳng chứ **không `useMemo`**: chỗ này nằm sau các `return` sớm của component, đặt hook ở đây là
hook có điều kiện. Danh mục giấy vài dòng, lọc không đáng kể.

Thêm một dòng phụ dưới ô (`.khsx-kv__hint`) nói vì sao danh sách ngắn — không thì người dùng tưởng
danh mục hỏng hoặc mất quyền: *"chỉ giấy đang dùng và giấy thay thế khai ở danh mục"*, hoặc *"chưa
khai giấy thay thế cho loại này ở danh mục nên không đổi được"* khi chỉ còn đúng một lựa chọn. Đường
đi tiếp nằm ở **danh mục**, không phải ở lệnh.

Ô này vốn là `<select>` nên **không có đường nhập liệu tự do** — đã soi lại DOM cụm quy cách: khoá
*Giấy* là `SELECT`, hai ô *Khổ giấy nguyên* là `INPUT[number]`, không có ô text nào cho tên giấy.

**TDD.** Thêm `test_o_giay_o_lenh_chi_mo_toi_giay_thay_the` vào
`backend/tests/test_khsx_ui_contract.py` (khoá cả `giayChonDuoc.map` lẫn *không còn* `giayRefs.map`,
option rỗng có điều kiện, hai câu hint) → ĐỎ → sửa FE → XANH.
`pytest tests/test_khsx_ui_contract.py` = **17 passed**; `npx tsc --noEmit` sạch; `npm test` =
**348 passed / 37 files**.

**Nghiệm thu bằng UI thật.** Không restart BE (không sửa backend); Vite HMR nhận FE.

*Nhánh MỞ — LSX26-0008 (giấy C150, `thay_the_ids = [4, 2]`, không giữ chỗ):* hamburger → **Kế hoạch
sản xuất** → tab **Lệnh sản xuất** → **Mở lệnh LSX26-0008** → tab **Quy cách**. Ô GIẤY liệt kê đúng
**3 dòng**: `Giấy C150 · 150 gsm` (đang chọn), `Giấy C200 · 200 gsm`, `Giấy C100 · 100 gsm` — khớp
`[4, 2]` cộng chính nó; **không có** dòng *"— chưa chọn giấy —"*, không có C250/C300; ô mở
(`disabled = false`), dòng phụ hiện *"chỉ giấy đang dùng và giấy thay thế khai ở danh mục"*. Đổi
sang **Giấy C100** → ĐỊNH LƯỢNG nhảy `150 → 100`, hiện **Hoàn tác / Lưu thay đổi**, và **danh sách
vẫn đúng 3 dòng** (chứng minh nó neo vào giấy đã lưu chứ không mở tiếp theo thay-thế-của-C100). Bấm
**Hoàn tác** → về `Giấy C150`, ĐỊNH LƯỢNG `150`, hết nút Lưu. **Không lưu gì.**

*Nhánh KHOÁ + neo khác — LSX26-0003 (giấy C300, `thay_the_ids = [5]`, đang giữ chỗ):* **Quay lại
danh sách lệnh** → **Mở lệnh LSX26-0003** → tab **Quy cách**. Ô GIẤY chỉ còn **2 dòng**:
`Giấy C300 · 300 gsm` + `Giấy C250 · 250 gsm` — danh sách bám theo từng lệnh, không phải một tập cố
định. Ô `disabled = true` cùng cả 9 ô input của cụm (khoá giữ chỗ của Task 22), dòng phụ không hiện
vì cụm đang chỉ-xem. Không cần soi thêm LSX26-0010: nó cùng neo C150 với 0008, mà vế khoá đã có
0003 chứng minh.

*Công cụ không phải chuột:* đúng **một** chỗ — `form_input` để đổi giá trị `<select>` ở LSX26-0008.
`<select>` gốc của Chrome bung popup **ngoài DOM**, CDP không lái được bằng phím; mọi bước còn lại
(mở sidebar, sang màn, mở lệnh, đổi tab, Hoàn tác, quay lại danh sách) đều là click thật.

*Log & dữ liệu:* từ mốc restart tới cuối — **0 dòng 409, 0 dòng 500**; request ghi vào LSX vẫn chỉ
là 2 lần `PUT /api/lsx/8` của Task 23, phiên này **không phát sinh PUT/DELETE nào**. Đọc lại DB
(`svn_erp_trong`, chỉ SELECT): `LSX26-0003 giay_id=3 gsm=300`, `LSX26-0008 giay_id=1 gsm=150
so_con=16` — nguyên trạng.

**Còn để lại (không sửa, chỉ ghi).** Danh mục giấy đang có mã nhân bản rõ ràng
(`GL-0001-COPY`, `GL-0001-COPY-COPY`); cả ba lệnh "Ruột sách 192 trang" đều chạy C150 150 gsm là
định lượng bìa chứ không phải ruột; LSX26-0008 có `so_trang = 1, trang_moi_tay = 1` trong khi
LSX26-0010 cùng tên sản phẩm là `192 / 32`. Đều là dữ liệu, không phải lỗi màn này.

## Task 25 — Quy cách ở lệnh: chỉ còn ô Giấy sửa được

**Yêu cầu.** *"Chỉ được chọn giấy."* Cụ thể: trong tab Quy cách của màn lệnh, ngoài ô Giấy ra
không ô nào chỉnh sửa được nữa.

**Trước đó.** Khi lệnh chưa giữ chỗ thì **cả cụm** sửa được — khổ giấy nguyên, khổ tờ, khổ thành
phẩm, cách in, số trang/tay, bleed, khe cắt, mực in, và cả **Bình bài** ở card *Máy tự tính*. Đó là
quyết định cũ "kế thừa từ phiếu tính giá = **mặc định**, không phải chỉ-xem"; lớp khoá duy nhất là
khoá giữ chỗ vật tư (Task 22), khoá theo **trạng thái** chứ không theo ô.

**Vì sao đổi.** Cụm này là thứ đã tính ra giá và **đã báo cho khách**. Gõ lại ở lệnh là lệnh chạy
một đằng, khách mua một nẻo, mà không có ai đối chiếu hai bên. Giấy là ngoại lệ duy nhất vì đổi giấy
không phải "đổi sản phẩm" mà là **chữa cháy khi hết hàng**, và đã bó vào danh sách thay thế khai ở
danh mục (Task 24).

*Đã nêu trước khi làm, người dùng chốt giữ nguyên phạm vi:* danh mục giấy **không lưu khổ** (mọi
dòng `kho_dai = kho_rong = 0`, bán theo kg) nên khổ giấy nguyên là số gõ tay tại lệnh — khoá nó lại
thì đổi sang giấy thay thế **khác khổ** vẫn tính số tờ/số kg theo khổ cũ. Ghi ra đây làm biên bản,
không phải để cãi lại quyết định.

**Sửa — chỉ FE.** `frontend/src/pages/LsxDetailView.tsx`:

| Chỗ | Trước | Sau |
| --- | --- | --- |
| Cờ quyền | `suaQc = canUpdate && !giuCho` gác 16 chỗ | `suaGiay = canUpdate && !giuCho` gác **đúng ô Giấy** |
| 10 ô số | `KVNum` (`<input type="number">`) | `KVSo` — **bỏ hẳn `<input>`**, hiện giá trị |
| Cách in | `<select>` 4 lựa chọn | chữ, qua `nhanCachIn()` |
| Mực in | `disabled={!suaQc}` | `disabled` cứng, `onChange` rỗng |
| Bình bài | `<input>` + `set("so_con", …)` | chữ |

`<input disabled>` bị loại có chủ ý: ô mờ đọc như *"tạm thời không bấm được"*, trong khi ở đây là
**không bao giờ** sửa ở màn này — bỏ ô nhập mới nói đúng.

Nhãn khối đổi thành *"thông số — chỉ xem, đổi được giấy khi thiếu hàng"*, và thêm một dòng chỉ
**đường đi tiếp** ngay trong khối: *"Thông số chụp từ phiếu tính giá lúc tạo lệnh và không sửa ở đây
— muốn đổi thì sửa ở phiếu tính giá rồi tạo lại lệnh (lệnh không tự bám theo phiếu). Riêng giấy đổi
được tại chỗ khi hết hàng."* Nói "chỉ xem" mà không nói đi đâu để đổi thật là mới xong nửa việc.

Băng khoá giữ chỗ viết lại cho khớp: giờ nó chỉ còn khoá **ô Giấy**, không phải "cả cụm thông số".

Tiện thể gộp nhãn cách in về một chỗ: `CACH_IN_NHAN` + `nhanCachIn()` chuyển vào
`keHoachSxShared.tsx`, xoá hai bản chép tay ở `BaiGhep2Page.tsx` và `LenhSxHoSoView.tsx` — chú thích
ở `BaiGhep2Page` vốn đã tự dặn *"đừng đẻ bộ thứ hai"* mà đang có ba bộ.

**Backend không đụng dòng nào.** `_chan_dang_giu_cho` vẫn là lưới cuối cho đường HTTP, và server vẫn
phải nhận `quy_cach` cho các cửa khác (bài ghép ép lại con/tờ). Màn lệnh chặt hơn server một nấc —
đúng hướng, không phải lệch.

**TDD.** Sửa `test_lenh_giu_cho_vat_tu_thi_thong_so_khoa_va_noi_ra` (đổi sang `suaGiay`, thêm
`assert "suaQc" not in source`) và thêm `test_quy_cach_o_lenh_chi_con_o_giay_sua_duoc` (không còn
`KVNum`, `source.count("setQc({") == 1`, không còn `set("so_con"`, hai câu microcopy) →
**2 failed** → sửa FE → `pytest tests/test_khsx_ui_contract.py` = **18 passed**.
`npx tsc --noEmit` sạch; `npm test` = **348 passed / 37 files**.

**Nghiệm thu bằng UI thật.** Không restart BE (không sửa backend); Vite HMR nhận FE.

*Nhánh MỞ — LSX26-0008 (không giữ chỗ):* hamburger → **Kế hoạch sản xuất** → tab **Lệnh sản xuất** →
**Mở lệnh LSX26-0008** → tab **Quy cách**. Đếm trong `#khsx-panel-quycach`: **0 ô `<input>`**, đúng
**1 `<select>`** là ô Giấy (mở, 3 lựa chọn C150/C200/C100 như Task 24). Toàn bộ 25 dòng còn lại là
chữ: `Khổ giấy nguyên 650 / 980`, `Khổ tờ 650 / 980`, `Khổ thành phẩm 160 / 240`,
`Cách in: 2 mặt (AB)` (nhãn dịch đúng từ khoá `hai_mat`), `Bleed 0`, `Khe cắt 0`, `Bình bài 16`.
Mười nút chip mực trong khối: **0 nút mở**. Nhãn khối và dòng chỉ đường hiện đúng chữ đã chốt.

*Ô giấy vẫn sống:* đổi ô Giấy sang **Giấy C100** → ĐỊNH LƯỢNG `150 → 100`, hiện **Hoàn tác / Lưu
thay đổi**, số lựa chọn vẫn 3, panel vẫn **0 input**. Bấm **Hoàn tác** → về `Giấy C150`, hết nút
Lưu. Không lưu gì.

*Nhánh KHOÁ — LSX26-0003 (đang giữ chỗ):* **Quay lại danh sách lệnh** → **Mở lệnh LSX26-0003** → tab
**Quy cách**: **0 input**, ô Giấy `disabled` với đúng 2 lựa chọn C300 + C250, băng hổ phách đọc
*"Lệnh đang giữ chỗ vật tư nên ô Giấy khoá luôn… Tên lệnh, hạn, ghi chú và cờ gấp vẫn sửa và lưu được
bình thường."* Sang tab **Thông tin chung** kiểm lại lời hứa đó: **3 ô nhập, cả 3 đều mở**.

*Công cụ không phải chuột:* đúng **một** chỗ — `form_input` để đổi giá trị `<select>` Giấy ở
LSX26-0008 (`<select>` gốc của Chrome bung popup ngoài DOM, CDP không lái được bằng phím). Mọi bước
còn lại là click thật.

*Log & dữ liệu:* từ mốc restart tới cuối — **0 dòng 409, 0 dòng 500**; request ghi vào LSX vẫn chỉ
là 2 lần `PUT /api/lsx/8` của Task 23, phiên này **không phát sinh PUT/DELETE/PATCH nào**. Đọc lại DB
(chỉ SELECT): `LSX26-0003 giay_id=3 gsm=300 kho_nguyen_dai=1090 so_con=9`,
`LSX26-0008 giay_id=1 gsm=150 kho_nguyen_dai=650 so_con=16` — nguyên trạng.

**Hệ quả để lại (biết trước, không vá).** Lệnh thiếu khổ thành phẩm (`thieu_kho`) hoặc thiếu giấy
(`thieu_giay`) nay **không còn đường tự bổ sung ở màn lệnh** — phải sửa ở phiếu tính giá rồi tạo lại
lệnh, và tạo lại là mất routing đã chỉnh. Dòng chỉ đường trong khối nói đúng chỗ phải tới, nhưng đây
là chỗ đầu tiên nên xem lại nếu người kế hoạch kêu vướng.

---

## Task 26 — Bản in báo giá: cùng tên sản phẩm gộp một dòng, nhiều mức số lượng

**Yêu cầu.** *"nếu cùng tên sản phẩm thì hợp lại thành 1 ô thôi, nhưng trong ô đơn giá thành tiền
và số lượng sẽ có nhiều mức"* — và chốt lại khoá gộp: *"ý là nó phải trùng tên sản phẩm đó nhé"*.
Phần chân bảng (Cộng tiền hàng · VAT · Tổng thanh toán) giữ nguyên như đang in.

**Chẩn đoán.** Báo giá bậc thang số lượng (một món, ba mức 10.000 / 20.000 / 50.000 cái) là ba dòng
`quote_items` riêng, `nhom` để trống. `utils/gop-nhom.ts` chỉ biết gộp theo nhãn `nhom` **và** cùng
SL, nên ba dòng đó in ra ba dòng lặp y hệt: ba lần tên, ba lần khổ, ba lần chuỗi công đoạn — khách
phải đọc chéo mới thấy chỉ khác mỗi con số.

**Cách sửa.** Thêm TẦNG GỘP THỨ HAI chạy sau `gopTheoNhom`, khoá là TÊN (chuẩn hoá trim +
hoa/thường), không đụng tầng cũ:

| File | Sửa gì |
| --- | --- |
| `frontend/src/utils/gop-nhom.ts` | Thêm `MucSoLuong`, `DongTheoTen<T>`, `gopTrungTen()`. Không cộng dồn SL (ba mức là ba phương án của cùng một món). VAT% / kích thước lệch giữa các mức ⇒ `null`. Diễn giải hợp nhất, bỏ gạch trùng. |
| `frontend/src/pages/BaoGiaPage.tsx` | `const dongIn = gopTrungTen(lines)`; thân bảng in mỗi mức một `<tr>`, ô STT · mô tả · ĐVT dùng `rowSpan={g.muc.length}`. Đơn giá vẫn tính tại chỗ `thanhTien / soLuong` (giữ 2 số lẻ) nên phép nhân trên giấy vẫn khớp. |
| `frontend/src/pages/bao-gia.css` | `tr.q-muc-tiep > td { border-top-style: dashed; }` — mức 2 trở đi ngăn bằng gạch đứt. |
| `frontend/src/pages/BaoGiaPage.tsx` (băng cảnh báo) | Băng "lệch số lượng" trước ghi *"sẽ in N dòng cho nhãn này"*; nay nhãn đó về lại một dòng nên đổi thành *"in nhãn này thành 1 dòng với N mức số lượng"*. |

**Phạm vi.** CHỈ bản in báo giá. Đơn hàng bán và phiếu giao hàng không đổi một chữ — ở phiếu giao,
số lượng là số giao thật, gộp thành mức là sai nghiệp vụ.

**Biên bản TDD.** Viết 7 test cho `gopTrungTen` trong `frontend/src/utils/gop-nhom.test.ts` trước →
chạy `npx vitest run src/utils/gop-nhom.test.ts` → **7 đỏ** (`gopTrungTen is not a function`), 8 test
cũ vẫn xanh → viết hàm → **15/15 xanh**. `npx tsc --noEmit` sạch.

**Biên bản nghiệm thu UI** (dev-browser tab `seed`, DB `svn_erp_trong`):

1. Mở **BG26-0006** (Sách bìa mềm 192 trang) → bấm **Xem bản in** → đọc DOM bảng in: **1 dòng**,
   không có `rowspan`, "Sách bìa mềm 192 trang, khổ 16x24cm" gộp bìa + ruột, 2.000 cuốn ·
   29.732,93 · 59.465.855. **Không hồi quy.**
2. Sidebar → **Tính giá** → **Lập phiếu tính giá** → **Thêm sản phẩm** → gõ `Hộp bánh` vào ô *Sản
   phẩm tái bản* → chọn **Hộp bánh 200g** (nạp lại cấu hình: LSP-0001 Hộp giấy bồi, 420×300) → gõ
   số lượng `10000` → **Xong**. Phiếu tự lưu thành **PTG-2026-0005**.
3. Bấm **Nhân bản sản phẩm** → drawer mở "Hộp bánh 200g (bản sao)" → sửa tên về `Hộp bánh 200g`,
   số lượng `20000` → **Xong**. Nhân bản lần nữa → sửa tên, số lượng `50000` → **Xong**.
4. Bấm **Tính giá** → ba dòng cùng tên: 10.000 / 2.363 đ · 20.000 / 2.242 đ · 50.000 / 2.127 đ
   (giá vốn đơn giảm dần theo SL — đúng bậc thang). KHÔNG tick ô "gộp khi báo giá" ⇒ `nhom` trống,
   đúng ca cần thử.
5. Bấm **Báo giá →** → sinh **BG26-0007** (nháp, 230.790.255 đ) → bấm **Xem bản in**.
6. Bảng in đọc từ DOM: **1 `<tr>` đầu** mang `rowspan=3` ở cả STT, ô mô tả và ĐVT; **3 mức**
   10.000 / 2.836,02 / 28.360.180 · 20.000 / 2.690,74 / 53.814.824 · 50.000 / 2.552,69 /
   127.634.319. Hai `<tr>` sau mang class `q-muc-tiep`, `borderTopStyle` = `dashed` (mức 1 =
   `solid`). Chân bảng: Cộng tiền hàng 209.809.323 · GTGT 10% 20.980.932 · Tổng 230.790.255 đ —
   **nguyên như cũ**.

**Tự khai.** Khung xem trước mang class `q-print-silent` (`display:none`) khi tài khoản có quyền in
— nó bắn thẳng `window.print()`, hộp thoại in của Chrome nằm ngoài DOM nên không chụp được. Để chụp
ảnh bản in, tôi **gỡ class đó khỏi element bằng JS ngay trên trình duyệt** (chỉ đổi hiển thị, không
sửa code, không thay bước nghiệp vụ nào). Mọi bước bấm/gõ ở trên đều là chuột + bàn phím thật.

**Còn để lại.** PTG-2026-0005 và BG26-0007 là dữ liệu dựng để nghiệm thu, **vẫn còn trong
`svn_erp_trong`** — giữ lại để xem lại bản in, xoá lúc nào cũng được.
