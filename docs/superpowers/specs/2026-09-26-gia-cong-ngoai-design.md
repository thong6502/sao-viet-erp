# Gia công ngoài — trọn gói & một phần — Thiết kế

**Ngày chốt:** 26/09/2026
**Phạm vi:** Kế hoạch SX (lệnh) · Phát hành SX · Thực hiện SX (bàn giao giữa công đoạn) · Kho
(xuất giấy, nhập thành phẩm) · Giao hàng · Phiếu chi · Xếp lịch 3 (chỉ bỏ phần ngày).
**Thay thế:** `docs/spec-thue-ngoai-giao-nhan.md` và quyết định 05/09 "nhà gia công khai thành máy".

---

## 1. Quyết định của chủ xưởng

> *"Nghiệp vụ tại nhà máy là có thể trọn gói cả lệnh và/hoặc một vài công đoạn."*
>
> *"Người lên kế hoạch sẽ là người mang đi gia công ngoài, và nó liên quan đến việc lập phiếu chi
> để ghi nhận dòng tiền ra khỏi công ty."*
>
> *"Gia công trọn gói tức là không phát lệnh xuống xưởng mà có chỗ để đi gia công luôn. Gia công một
> phần, vd in xong mới đem đi, gia công xong thì về làm tiếp."*
>
> *"Không muốn hệ thống liên quan gì tới hạch toán hay sổ kế toán như 331. Đừng quá phức tạp, đừng
> liên quan đến ngày hẹn về."*
>
> *"Trọn gói có trường hợp nhà gia công chuyển thẳng hàng cho khách. Không cần KCS trên phần mềm,
> KCS có thể ngoài phần mềm nhưng cần người nhập con số cuối cùng."* (26/09/2026)

Một câu: **mọi lần gia công ngoài kết thúc bằng MỘT con số do người nhập; con số đó rẽ về xưởng,
về kho, hoặc thẳng tới khách. Phần mềm không KCS, không ngày hẹn, không công nợ.**

## 2. Khái niệm duy nhất: LẦN GIA CÔNG

Một **lần gia công** = một nhà gia công + một khối việc đem ra ngoài, gửi một lần, chốt một con số.

| Kiểu | Khối việc | Ví dụ |
|---|---|---|
| **Một phần** | một dải bước LIỀN NHAU của lệnh, cùng một nhà gia công | cán màng; hoặc bế + dán cùng một xưởng hộp |
| **Trọn gói** | cả lệnh, không phát hành xuống xưởng | đặt in hộp ở nhà in khác |

Luật gộp dải: các bước "Thuê ngoài" **liền nhau, cùng nhà gia công** là **một lần** — gửi đi tờ
của bước đầu, nhận về sản phẩm của bước cuối. Khác nhà gia công hoặc chen một bước nội bộ ở giữa
là hai lần.

Mỗi lần giữ đúng các thứ sau, không hơn:

| Nhóm | Ô | Ai nhập / nguồn |
|---|---|---|
| Đặt | Nhà gia công | chọn từ danh mục **Nhà cung cấp** — chỉ nhà cung cấp đang hoạt động có tích **Nhận gia công** (§7) |
| | Đơn giá (theo đơn vị của con số cuối) | kế hoạch nhập, bỏ trống được |
| | Số lượng đặt | chỉ trọn gói — điền sẵn số của lệnh |
| | Xưởng cấp giấy? | chỉ trọn gói — có / không |
| Mang đi | Người · giờ · số gửi | chỉ một phần — người + giờ lấy từ tài khoản, số điền sẵn |
| Chốt | Người · giờ · **con số cuối** · **nơi về** (xưởng / kho / khách) | người + giờ từ tài khoản |

**Dẫn xuất, không lưu:** trạng thái (*chờ mang đi* → *đang ở ngoài* → *đã xong*; trọn gói:
*đang gia công* → *đã xong*) · tiền = con số cuối × đơn giá.

**Không có:** ngày gửi dự kiến, ngày hẹn về, số ngày vận chuyển/gia công, hao hụt cho phép, KCS,
công nợ, nhiều chuyến cho một lần.

## 3. Luồng MỘT PHẦN — ví dụ In → Cán màng (ngoài) → Bế → Đóng gói

| # | Ai | Làm gì | Hệ ghi / hiện |
|---|---|---|---|
| 1 | Kế hoạch | Bước Cán màng chọn loại **Thuê ngoài** → chọn nhà gia công, nhập đơn giá. Không chọn máy, không chọn tổ. | Bảng "còn thiếu" nhắc nếu chưa chọn nhà gia công. |
| 2 | Kế hoạch | Phát hành lệnh như thường. | Hệ tạo **lần gia công** cho dải Cán màng, trạng thái *chờ mang đi*. |
| 3 | Tổ in · Kho | Tổ in đề nghị giấy, kho xuất — y như hiện nay. | — |
| 4 | Tổ in | Chạy In, ghi sản lượng, bàn giao 1.660 tờ sang Cán màng. | Người kế hoạch nhận **thông báo tức thì**: "LSX… có 1.660 tờ chờ mang đi cán màng". |
| 5 | Kế hoạch | Chở hàng đi, bấm **Đã mang đi** (số điền sẵn 1.660) → Lưu. | Nút này = nhận bàn giao từ In. Ghi "Nguyễn A mang đi 1.660 tờ lúc 26/09 14:20". Trạng thái *đang ở ngoài*. Tổ bế thấy Bế "chờ hàng gia công về". |
| 6 | Kế hoạch | Lấy hàng về, tự kiểm ngoài phần mềm, bấm **Đã nhận về** → gõ số cuối 1.650. Nơi về tự là *xưởng*. | Dải Cán màng xong với số ra 1.650; hệ đề xuất bàn giao 1.650 tờ sang Bế. Kế toán nhận thông báo "có lần gia công chờ chi". |
| 7 | Tổ bế | Xác nhận nhận bàn giao như thường, làm Bế, rồi Đóng gói. | Đầu vào Bế = 1.650 (số thực về, không phải 1.660). |
| 8 | Xưởng | Đóng gói là bước cuối → KCS → nhập kho thành phẩm → giao khách. | Không đổi gì. |
| 9 | Kế toán | Lập phiếu chi, chọn lần gia công này. | Số tiền 1.650 × đơn giá điền sẵn, sửa được. |

**Dải là bước cuối của lệnh** (vd đóng gói ngoài): ở bước 6 người chốt chọn nơi về **kho** hoặc
**khách** — đi tiếp như §4 bước 4–5. Không qua KCS trên phần mềm.

**Vật tư của bước thuê ngoài:** mặc định bên gia công tự lo (tiền nằm trong đơn giá) ⇒ bước thuê
ngoài **không có dòng vật tư**, không giữ chỗ, không vào kế hoạch vật tư. Nếu lần nào xưởng đưa vật
tư (vd màng) thì kế hoạch lập **đề nghị xuất kho thường** ghi lệnh — không đẻ đường riêng.

**Tờ in đi/về KHÔNG qua kho**: hệ không theo dõi tồn bán thành phẩm (đã gỡ 17/09, mg 0308).

## 4. Luồng TRỌN GÓI

| # | Ai | Làm gì | Hệ ghi / hiện |
|---|---|---|---|
| 1 | Kế hoạch | Lệnh tạo từ đơn như thường. Ở lệnh chưa phát hành (đã xếp lịch thì hệ tự gỡ lịch), bấm **Gia công trọn gói** thay cho phát hành → chọn nhà gia công, đơn giá, số đặt (điền sẵn), xưởng cấp giấy có/không. | Lệnh sang *gia công trọn gói*: trên sổ nó là lệnh đã thả đi với MỘT việc duy nhất "Gia công trọn gói — ‹nhà gia công›", không tổ nào nhận ⇒ không vào bàn tổ, không vào Xếp lịch, không khoán, nhưng vẫn hiện ở màn Theo dõi SX. Routing của lệnh không cần khai. Lệnh đang ghép cụm với lệnh khác (cùng nhóm thành phẩm / bài ghép) thì chưa cho trọn gói. |
| 2a | Kế hoạch · Kho | **Nếu xưởng cấp giấy:** bấm **Đề nghị xuất giấy** trên lần gia công → hệ lập đề nghị xuất kho sẵn dòng giấy của lệnh, người nhận = người kế hoạch, ghi chú "Cấp giấy gia công trọn gói — ‹nhà gia công›". Kho xuất như mọi đề nghị. | Giữ chỗ giấy của lệnh được tiêu như thường. Phiếu xuất kho là vết giấy rời công ty — **không có nút "Đã mang đi"** cho trọn gói. |
| 2b | — | **Nếu nhà gia công tự lo giấy:** không làm gì. | Lệnh thôi đòi giấy: nhả giữ chỗ, kế hoạch vật tư bỏ nhu cầu giấy của lệnh. |
| 3 | Kế hoạch | Hàng xong, tự kiểm ngoài phần mềm, bấm **Chốt** → gõ con số cuối + chọn nơi về. | Kế toán nhận thông báo "có lần gia công chờ chi". |
| 4 | Kho → Giao hàng | **Nơi về = kho:** hệ tự lập **đề nghị nhập kho thành phẩm** (mã thành phẩm của dòng đơn) theo con số cuối, **không qua KCS**. Kho ghi sổ. Sau đó giao khách như đơn thường. | Số nhập này tính vào "giao được" của đơn như hàng xưởng làm. |
| 5 | — | **Nơi về = khách** (nhà gia công giao thẳng): con số cuối = số khách nhận; ngày giao = giờ chốt. | Hệ ghi một yêu cầu giao + một lần giao *thành công* ghi rõ "nhà gia công giao thẳng", đứng tên người chốt ⇒ cộng vào **"đã giao"** của dòng đơn. Không kho, không xe, không phiếu xuất, không tính tiền km. Đơn vẫn hiện *giao đủ* để kế toán xuất hoá đơn. Chỉ cho khi dòng đơn của lệnh đứng riêng một cụm bán. |
| 6 | Kế toán | Lập phiếu chi từ lần gia công. | Tiền điền sẵn, sửa được (vd trừ hàng lỗi). |
| 7 | — | Lần đã chốt ⇒ lệnh **xong**. | — |

**Huỷ trọn gói:** trước khi chốt, kế hoạch bấm **Huỷ gia công trọn gói** → lệnh về *sẵn sàng*,
phát hành nội bộ được. Giấy đã xuất thì nhập trả kho theo đường thường, hệ không tự đảo.

Một lần chỉ về **một nơi**. Nhà gia công vừa giao khách một phần vừa chở về kho một phần ⇒ tách
hai lần.

## 5. Phiếu chi — chỉ ghi tiền ra

- Phiếu chi thêm **nguồn thứ tư "Gia công ngoài"**, cạnh Phiếu mua hàng · Tạm ứng lương · Khác.
  Chép đúng khuôn tạm ứng lương đang chạy: chọn nguồn → chọn lần gia công đã chốt → số tiền, người
  nhận (nhà gia công, hoặc người kế hoạch nếu họ cầm tiền mặt đi trả), lý do chi ("Gia công ‹công
  đoạn› — LSX… — ‹nhà gia công›") điền sẵn.
- Số tiền **sửa được** — phiếu chi là số thật đã trả; con số trên lần gia công chỉ là gợi ý.
- Luật phiếu chi giữ nguyên: lập ra là tiền đã ra, không sửa, chỉ huỷ. **Một lần gia công — một
  phiếu chi** (huỷ thì lập lại). Cọc / chi nhiều đợt: không làm.
- Danh sách chọn chỉ hiện lần đã chốt mà chưa có phiếu chi còn sống — đó là toàn bộ "chờ chi".
- **Không dính 331:** phiếu chi nguồn Gia công ngoài **để trống ô nhà cung cấp công nợ**
  (`supplier_id`), tên nhà gia công chỉ nằm ở người nhận / lý do chi, và **bị loại khỏi báo cáo
  công nợ phải trả (331)** cùng sổ chi tiết. Không tuổi nợ, không
  hạn trả, không số "còn phải trả".
- Người lập phiếu chi là kế toán (quyền phiếu chi sẵn có). Người đặt gia công không tự lập phiếu chi.

## 6. Người, quyền, thông báo, nhật ký

- **Ai bấm Mang đi / Chốt / Gia công trọn gói / Đề nghị xuất giấy:** ai có quyền sửa lệnh
  (`san_xuat:update`). Không thêm vai, không thêm bit.
- **Tiền:** đơn giá và tiền trên lần gia công đi qua cổng quyền xem tiền ở máy chủ như mọi số tiền
  khác ⇒ vai Kế hoạch phải được cấp quyền xem tiền, không thì chính người nhập giá không thấy giá.
- **Thông báo tức thì (đẩy SSE):**
  - tới người có quyền sửa lệnh khi bước trước bàn giao sang dải thuê ngoài ("chờ mang đi") —
    toast; badge Kế hoạch SX vẫn là hàng chờ đơn, không trộn thêm;
  - tới người có quyền lập phiếu chi khi một lần được chốt ("chờ chi") — toast + badge số lần chờ
    chi treo ở mục **Phiếu chi** của thanh bên (không dùng kênh badge `ke_toan` — kênh đó gắn màn
    Đơn mua hàng). Lập / huỷ phiếu chi nguồn gia công cũng đẩy tín hiệu để badge của người khác
    nhảy theo.
- **Nhật ký:** mỗi lần Đặt · Mang đi · Chốt · Mở lại · Huỷ · Đề nghị xuất giấy ghi `audit_logs` (ai,
  lúc nào, số bao nhiêu), hiện ngay trên lần gia công. Không xoá vết cũ.
- **Sửa con số cuối = Mở lại rồi chốt lại.** Mở lại chỉ được khi chứng từ phía sau chưa chạy (bàn
  giao sang bước sau chưa được xác nhận, đề nghị nhập kho chưa lập phiếu, phiếu chi chưa lập). Đã
  chạy thì huỷ chứng từ sau trước. Mở lại gỡ sạch những gì lần chốt đã đẻ ra.

## 7. Màn hình

- **Hồ sơ Nhà cung cấp (Mua hàng):** thêm ô tích **Nhận gia công**. Không lọc theo chữ ô "Nhóm"
  (gõ tự do — "GC ngoài", "gia cong" là lọt). Nhà gia công mới do bên mua hàng tạo ở màn này như
  mọi nhà cung cấp; ô chọn ở Kế hoạch **không** có nút thêm nhanh. Danh sách trống ⇒ ô chọn nhắc
  "vào màn Nhà cung cấp tích *Nhận gia công*".
- **Drawer bước (Kế hoạch SX):** chọn "Thuê ngoài" ⇒ tab Phân công thay khối Tổ/Máy bằng **Nhà
  gia công** (danh mục Nhà cung cấp) + **Đơn giá**. Tab Tiến độ bỏ "Số lượt chạy qua máy". Bước liền
  trước cùng nhà gia công ⇒ hiện "đi chung một lần với ‹bước›"; ô đơn giá chỉ hiện ở bước cuối dải
  ("đơn giá cả lần, theo ‹đơn vị ra›").
- **Lệnh sau phát hành / lệnh trọn gói:** khối **Gia công ngoài** trên lệnh — mỗi lần một dòng:
  nhà gia công · trạng thái · nút kế tiếp (Mang đi / Đã nhận về / Chốt) · dòng tóm tắt sau khi xong
  ("Nguyễn A mang đi 1.660 · Nguyễn A nhận về 1.650 · 247.500đ"). Mini-form điền sẵn — hai click.
- **Danh sách Kế hoạch SX:** thêm bộ lọc **Gia công ngoài** (chờ mang đi / đang ở ngoài / đang gia
  công trọn gói) — lọc ở máy chủ.
- **Sơ đồ / bảng bước, Xếp lịch, bàn tổ:** chỉ nhìn trạng thái + nhảy về lệnh. Một cửa ghi duy nhất.
- **Phiếu chi:** thêm nguồn "Gia công ngoài" vào hộp lập phiếu.

## 8. Lịch & thời lượng

Bước thuê ngoài **không có thời lượng**: Kế hoạch SX thôi tính theo tốc độ máy; Xếp lịch 3 tính dải
thuê ngoài = 0 và ghi chú "không tính thời gian gia công ngoài". Lệnh trọn gói không vào Xếp lịch.
Ngày kết thúc dự kiến vì thế là ngày *xưởng làm xong phần của mình* — đúng ý "không dính ngày hẹn về".

## 9. Không làm (đợt này)

- Ngày gửi/hẹn về, cảnh báo quá hạn, hao hụt cho phép, detector "thuê ngoài trễ".
- KCS trên phần mềm cho hàng gia công ngoài.
- Công nợ nhà cung cấp, 331, tuổi nợ, cọc, chi nhiều đợt, đi qua Phiếu mua hàng.
- Theo dõi tồn tờ in đang nằm ở nhà gia công.
- Báo giá / phiếu tính giá: giữ nguyên cách tính bước thuê ngoài bằng công thức nội bộ.
- **Bài ghép 2** (bước chung thuê ngoài của nhiều lệnh): **đợt 2** — cùng cơ chế, lần gia công gắn
  bài ghép thay vì lệnh; khi làm thì gỡ luôn tab "Gia công ngoài" cũ của bước chung.

## 10. Phụ lục kỹ thuật — chỗ phải sửa

Dự án chưa có dữ liệu thật ⇒ ưu tiên ĐÚNG, không giữ tương thích cột cũ.

**Dữ liệu** (viết `db_migrations.py` + cập nhật `docs/DB_SCHEMA.md` cùng lúc):
- Bảng mới `gia_cong_ngoai` (một dòng = một lần): `lsx_id`, `kieu` (mot_phan | tron_goi),
  `nha_cung_cap_id` → `suppliers`, `don_gia`, `don_vi` (ảnh chụp), `sl_dat`, `xuong_cap_giay`,
  `mang_di_boi_id`, `mang_di_luc`, `sl_gui`, `chot_boi_id`, `chot_luc`, `sl_cuoi`, `noi_ve`
  (xuong | kho | khach), `huy_luc`/`huy_boi_id`, dấu thời gian. *Vì sao một bảng:* một lần phủ
  NHIỀU bước (dải) hoặc KHÔNG bước nào (trọn gói) — cột trên từng bước không chở nổi.
- `suppliers.nhan_gia_cong` Boolean, `server_default=false` (bool Python, không phải `"0"` —
  vỡ Postgres). Ô chọn nhà gia công đọc qua một cửa gọn (id + tên, lọc cờ này + đang hoạt động)
  dưới quyền `san_xuat:read` — người kế hoạch không cần quyền Mua hàng.
- `lsx_cong_doan`: thêm `nha_cung_cap_id` (tham chiếu mềm như mọi FK danh mục khác của lệnh —
  máy, tổ, khuôn); cột chữ `nha_cung_cap`
  **giữ làm tên hiển thị do máy chủ ghi** theo nhà gia công đã chọn (client không gửi) — bảy chỗ
  đang đọc tên (snapshot, hồ sơ lệnh, phiếu công nghệ, chip…) khỏi phải đổi. **Giữ**
  `don_gia_gia_cong`; **gỡ** `sl_gui`, `ngay_gui_dk`, `van_chuyen_ngay`, `gia_cong_ngay`,
  `ngay_nhan_dk`, `hao_hut_cho_phep`, `yeu_cau_ky_thuat` (dùng `ghi_chu` sẵn có), và 6 cột
  giao–nhận thực (`nguoi_giao_id`, `giao_luc`, `sl_giao_thuc`, `nguoi_nhan_id`, `nhan_luc`,
  `sl_nhan_thuc`).
- `san_xuat_cong_viec`: thêm `gia_cong_ngoai_id` (các cv của dải); ảnh chụp `nha_cung_cap` giữ làm
  tên hiển thị.
- **Trọn gói KHÔNG thêm trạng thái lệnh.** Bấm trọn gói = phát hành một gói chỉ có MỘT công việc
  thuê ngoài không tổ (`department_id` NULL, `la_kcs_cuoi` = true, đơn vị = đơn vị thành phẩm của
  dòng đơn). Nhờ vậy nhóm thành phẩm, đóng nhóm, trạng thái lệnh ở Theo dõi SX, nhập kho, giao hàng
  chạy nguyên đường cũ. Huỷ trọn gói = thu hồi gói (`release_update.thu_hoi_goi`) + lệnh về sẵn
  sàng/nháp. Chặn luôn cửa `set_trang_thai` nhận `da_phat_hanh` từ client.
- **Số chốt thay cho KCS:** khi dải chứa bước cuối lệnh (hoặc trọn gói), chốt ghi một mẻ sản lượng
  (tốt = số chốt) và một bản ghi KCS đạt = số chốt đứng tên người chốt, ghi chú "KCS làm ngoài phần
  mềm". Giữ `la_kcs_cuoi` như thường ⇒ đóng nhóm, "còn gửi kho", trạng thái lệnh không phải rẽ
  nhánh. Cửa KCS chặn kiểm công việc gia công; báo cáo KCS loại các bản ghi này.
- Người ghi trên `gia_cong_ngoai` (`created_by`, `mang_di_boi_id`, `chot_boi_id`, `huy_boi_id`) là
  tham chiếu MỀM tới `users` (không FK) — FK tới `users` trong dự án bắt buộc CASCADE, xoá tài khoản
  không được kéo mất lần gia công.
- Tham chiếu mềm `gia_cong_ngoai_id` trên: `stock_requests` (xuất giấy trọn gói, nhập thành phẩm),
  `delivery_trips` (giao thẳng — `khoan_km_service` loại chuyến này khỏi tiền km),
  `payment_vouchers` (nguồn mới, FK + unique một phiếu còn sống).
- Migration: `0337_gia_cong_ngoai` (thêm) và `0338_go_cot_thue_ngoai_cu` (gỡ cột cũ của bước).

**Luồng:**
- Phát hành (`san_xuat/release.py`, cập nhật phát hành): gộp dải thuê ngoài → tạo/giữ lần gia
  công; cv thuê ngoài không vào bàn tổ nào.
- `thuc_thi.bat_dau` đang bắt gán thợ khoán — cv thuê ngoài **không đi qua bắt đầu/mẻ**; Mang đi =
  xác nhận nhận bàn giao (`ban_giao.xac_nhan`), Đã nhận về = ghi số ra của dải + `ban_giao.de_xuat`
  sang bước sau. Gỡ `doi_may` cho thuê ngoài.
- Nhập kho không qua KCS: `san_xuat/kho.tao_yeu_cau_nhap_kho_cong_doan` đòi `gate_kcs` — tách
  lõi lập đề nghị ra hàm không gate, lần gia công gọi lõi đó với cv cuối của lần (đề nghị vẫn mang
  `san_xuat_cong_viec_id` ⇒ `delivery_repo.dong_nhap_tp_cua_lenh` đếm được, khỏi sửa). Bản ghi KCS
  tổng hợp lúc chốt làm "còn gửi kho" và đóng nhóm chạy nguyên.
- Giao hàng: giao thẳng ghi một yêu cầu giao + một chuyến *thành công* (mang `gia_cong_ngoai_id`)
  để `da_giao_theo_dong` cộng vào; đi thẳng qua repo, không qua cửa lập chuyến (cửa đó chặn theo
  trần "giao được" tính từ kho).
- Vật tư: `lsx_service._bung_vat_tu_cong_doan` phải bỏ qua bước thuê ngoài như `_bung_lai_vat_tu`
  đang làm; trọn gói + nhà gia công lo giấy ⇒ nhả giữ chỗ, `ke_hoach_vat_tu` bỏ nhu cầu của lệnh.
- Thời lượng: `lsx_service.thoi_luong_buoc` thôi đi nhánh máy cho thuê ngoài; bỏ
  `xep_lich/service._ngay_thue_ngoai`.
- Phiếu chi: nguồn `gia_cong_ngoai` chép khuôn `salary_advance_id` trong `accounting_service`
  (kiểm nguồn, điền sẵn; huỷ phiếu không có gì phải trả về — lần gia công tự hiện lại "chờ chi");
  `accounting_repo.phieu_chi_cho_bao_cao` (nguồn của báo cáo 331) loại nguồn này.
- Gỡ: cửa ghi cũ `POST /api/lsx/{id}/buoc/{buoc_id}/giao-nhan` + `ghi_giao_nhan` +
  `_giao_nhan_dict`; `api.lsx.giaoNhan`; CSS `.khsx-gn*`; `ChipNgoai` không ai dùng.
- Guard `test_khsx_ui_contract.test_thue_ngoai_khong_co_o_nao_rieng_ngoai_buoc_may` thay bằng
  guard mới: bước thuê ngoài có ô Nhà gia công, không có ô Máy/Tổ.
