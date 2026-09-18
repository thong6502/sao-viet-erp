# Thiết kế — Nhập kho thành phẩm đi qua "Yêu cầu nhập xuất"

> Bàn 17/09/2026, **đã làm 17/09/2026** (mg `0309` thêm cột, `0310` drop ba bảng `san_xuat_kho*`).
> Plan: `docs/superpowers/plans/2026-09-17-nhap-kho-thanh-pham.md`.
> Liên quan: `docs/design-kcs-theo-lenh.md` §6, `docs/prd-thanh-pham.md`, `docs/spec-thuc-hien-san-xuat.md` §14.

## 0. Kết luận và một chỗ sửa lại so với "hướng A"

Mục tiêu của hướng A giữ nguyên: KCS gửi nhập kho thành một **yêu cầu NHẬP thật** trong module
"Yêu cầu nhập xuất". Thủ kho nhận hàng bằng phiếu nhập như mọi hàng khác. Giao hàng xuất kho
**đúng mặt hàng đó, trong cùng một sổ**.

Chỗ sửa: **không thêm loại mặt hàng thứ ba.** Khảo sát cho thấy hệ đã có sẵn thứ hướng A định dựng:

- Danh mục **Thành phẩm** (`vat_tu_in_an.la_thanh_pham = true`, mã `TP-00001…`) được tự khai lúc
  chốt đơn, mỗi dòng đơn một món.
- Giao hàng **đang** xuất kho đúng các món `TP-…` này (`delivery_service.tao_yeu_cau` →
  `khai_mot_dong`).
- Sổ kho coi chúng là `hang_loai = "vat_tu"`. Việc không đẻ `hang_loai` thứ ba là **cố ý, đã đo**
  (`prd-thanh-pham.md` §2): có 4 cổng chặn, 3 bảng tra, gần chục schema regex `giay|vat_tu`, và vài chỗ rẽ
  hai nhánh "không phải giấy thì là vật tư". Riêng chỗ giữ chỗ (`giu_cho_service:786`) sẽ khoá
  nhầm bảng.

Hướng A đúng nghĩa vì vậy chỉ là **nối KCS vào món Thành phẩm đã có**. Chỗ hỏng hiện nay chỉ nằm ở
khúc giữa: sản xuất nhập vào một sổ riêng (`san_xuat_nhap_kho_yc` / `san_xuat_kho_lot`) mà sổ kho
thật không biết. Giao hàng thì xuất từ sổ thật, nơi món `TP-…` chưa từng được nhập.

## 1. Vì sao phải đổi

| Hiện nay | Hậu quả |
|---|---|
| KCS gửi → `san_xuat_nhap_kho_yc`; kho bấm xác nhận → `san_xuat_kho_lot` | Tồn kho thật không có thành phẩm. Phiếu xuất của Giao hàng trừ vào món `TP-…` có tồn 0. |
| Nút xác nhận của kho nằm ở thanh "Kho chờ xác nhận" trên **mọi** Bàn tổ (ai có `kho:read` cũng thấy) | Tổ nào cũng thấy hàng chờ của cả công ty; thủ kho phải giữ dòng quyền tổ SX mới vào được bàn tổ. |
| Kho có hai hộp thư: "Hộp yêu cầu" và thanh trên bàn tổ | Việc của kho rải hai nơi, báo cáo nhập–xuất–tồn không có hàng sản xuất. |
| Lot thành phẩm neo NHÓM, không neo lệnh | `boi_canh` / `trang_thai` phải đi vòng qua nhóm để trả lời "lệnh này nhập kho chưa". Giao hàng chỉ tính được trần khi nhóm là 1 lệnh – 1 dòng đơn – 1 món. |

## 2. Luồng mới

```
KCS (màn KCS · công đoạn cuối)
  [Tạo yêu cầu nhập kho]  — server tự tính phần ĐẠT chưa gửi, không nhận số từ client
        │
        ▼
YÊU CẦU NHẬP XUẤT   DNNxxxxx · loại NHẬP · tự duyệt · người tạo = người KCS
  dòng: TP-00012 Kỷ yếu 25 năm An Phát · LSX26-0005 · 500 cuốn · giá gốc 0 đ · giá bán 23.000 đ/cuốn
        │  (chuông + đẩy SSE cho kho — cơ chế sẵn có của Yêu cầu nhập xuất)
        ▼
KHO · Hộp yêu cầu → Lập phiếu nhập (chọn kho, nhận một phần được) → Ghi sổ
        │  → lô TP-00012 · nguồn LSX26-0005 / DH019 · giá gốc 0 đ ("chưa có giá gốc")
        │
        ├──► KẾ TOÁN KHO (lúc nào biết giá) → mở lô, gõ giá gốc → báo cáo kho tự tính lại
        ▼
GIAO HÀNG DH019 → chọn cụm "Kỷ yếu" 500 cuốn → phiếu XUẤT TP-00012, gợi ý lô của DH019 → trừ tồn
```

Những gì sản xuất cần biết ("đã gửi bao nhiêu", "kho đã nhận bao nhiêu") được **đọc ngược** từ yêu
cầu kho. Không còn sổ thứ hai và không có bước chép số.

## 3. Mặt hàng nào được nhập

**Luật: kho giữ đúng thứ khách mua.** Mã thành phẩm khai theo **cụm bán**, dùng đúng luật gộp
dòng đang áp cho bản in báo giá và xác nhận đơn (`frontend/src/utils/gop-nhom.ts`, chốt 26/08/2026):

- Dòng đơn **không có nhãn nhóm**: một dòng = một cụm = một mã, như hiện nay.
- Các dòng **cùng nhãn nhóm và cùng số lượng** (vd Ruột 500 + Bìa 500): **một** mã cho cả cụm.
  - Tên mã = nhãn nhóm ("Kỷ yếu 25 năm An Phát").
  - Đơn vị = ĐVT cụm (`dvt_nhom`, vd "cuốn"); bỏ trống thì lấy ĐVT dòng đầu cụm.
  - SL cụm = SL dòng đầu cụm, không cộng dồn.
- Cùng nhãn mà khác số lượng thì bản in tách dòng, nên kho cũng tách mã.

Chốt đơn (`khai_cho_don`) khai theo cụm thay cho từng dòng. Dòng đơn trong cụm trỏ về mã của cụm.

Nhập từ KCS:

- Nhóm sản xuất trùng một cụm (ca thường gặp): **một** dòng yêu cầu, SL = số đạt.
- Nhóm sản xuất gom theo nhãn mà không xét số lượng. Nếu một nhóm chứa hai cụm (cùng nhãn, khác
  SL), KCS nhập vào từng mã theo tỉ lệ SL cụm / SL của lệnh thân chính.
- `dong_yeu_cau.lsx_id` = lệnh thân chính. Cột này đã có, và Hộp yêu cầu của kho đã hiện mã lệnh.

Giao hàng với cụm:

- Người lập yêu cầu giao chọn **cụm** và gõ số lượng một lần (500 cuốn).
- Hệ ghi "đã giao 500" cho **mọi dòng** trong cụm, để đơn vẫn biết Ruột và Bìa đã giao đủ.
- Phiếu xuất kho có **một** dòng: mã cụm, 500 cuốn.
- Chỉ dòng đầu cụm mang mã thành phẩm trên yêu cầu giao. Các dòng còn lại không xuất kho riêng,
  không thì kho bị trừ hai lần.

**Đơn vị.** Dòng yêu cầu ghi theo đơn vị của món (`don_vi_gia`). Số đạt của KCS tính theo đơn vị ra
của công đoạn cuối; nếu hai đơn vị khác nhau thì quy đổi qua `quy_doi_service` như mọi dòng kho.
Có hai trường hợp chặn, báo bằng lời nghiệp vụ:

- Món chưa có đơn vị (dòng đơn gõ đơn vị lạ): *"Thành phẩm TP-00012 chưa khai đơn vị — khai ở
  Cấu hình danh mục ▸ Thành phẩm rồi gửi lại."*
- Không quy đổi được: *"Không quy đổi được từ «tờ» sang «cuốn» cho TP-00012."*

## 4. Số lượng và trần

Tính theo **công đoạn cuối**, không theo từng lần kiểm. Yêu cầu kho không có chỗ neo lần kiểm, và
chẳng màn nào cần số theo lần kiểm.

```
được gửi thêm = min(Σ đạt của công đoạn, Σ tốt tổ đã ghi) − Σ đã đề nghị còn hiệu lực
```

- "Đã đề nghị còn hiệu lực" đọc trên dòng yêu cầu của **lệnh thân chính**, trong các yêu cầu có
  nguồn là công đoạn này:
  - yêu cầu còn sống: lấy `StockRequestService.muc_tieu_hieu_luc(dòng)`, tức số kho đã chốt nếu
    có, không thì số đề nghị;
  - yêu cầu **đã huỷ / bị từ chối**: chỉ tính `sl_da_ung`.
- Hệ quả: kho huỷ yêu cầu hoặc chốt nhận thiếu thì phần chưa nhận **tự quay về** cho KCS gửi lại,
  không cần nút riêng.
- Chặn bấm đúp giữ như nay: khoá dòng các lần kiểm của công đoạn (`FOR UPDATE`) rồi mới đọc số, và
  tạo yêu cầu bằng `create(commit=False)` trong cùng giao dịch. Thông báo cho kho gửi sau khi commit
  (`thong_bao_yeu_cau_moi`), đúng khuôn `vat_tu_de_nghi.tao()`.
- Không còn gì để gửi thì trả 409 với câu như nay.

## 5. Dữ liệu

**Thêm 4 cột** (đều nullable, soft ref, không FK; migration + dòng trong `docs/DB_SCHEMA.md`):

- `stock_requests.san_xuat_cong_viec_id` (Integer, index) — nguồn là công đoạn cuối. Cùng khuôn với
  `purchase_delivery_id` / `delivery_trip_id`, và phải thêm vào `_HEADER_FIELDS`
  (`stock_request_repo.py:28`), nếu không repo lặng lẽ bỏ cột.
- `stock_request_lines.don_gia_ban` (BIGINT) — xem "Giá trị" bên dưới.
- `stock_lots.lo_goc_id` và `stock_voucher_lines.lo_goc_id` (Integer, index) — xem "Kho là danh mục
  động" bên dưới.

Yêu cầu tự ghi `ghi_chu`: *"Nhập thành phẩm từ KCS · LSX26-0005 · Kỷ yếu 25 năm An Phát"*, để kho
đọc ra nguồn mà không cần thêm ô nào trên màn.

**Bỏ cả sổ kho riêng của sản xuất:** ba bảng `san_xuat_nhap_kho_yc`, `san_xuat_kho_lot`,
`san_xuat_kho_hang`. BTP đã gỡ (mg `0308`), nên ba bảng này nay chỉ còn chứa thành phẩm và không
còn ai cần. DB dev hiện có **1** yêu cầu, **0** lot, **1** dòng hàng (đếm lại 17/09/2026). Dự án
chưa có dữ liệu thật nên xoá, không chuyển; sau khi drop thì không khôi phục được.

**Giá trị — mỗi lô thành phẩm mang HAI giá (chủ chốt 17/09/2026).**

Phần mềm không tính được giá gốc (chi phí thật để làm ra một sản phẩm). Số "giá vốn" trên dòng đơn
(`cost_snapshot`) chỉ là nền tính giá của phiếu tính giá: trên DB dev 14/15 dòng đơn có thành tiền
đúng bằng nền × 1,2 (vd dòng #8: 26.712.204 × 1,2 = 32.054.645), dòng còn lại là giá sửa tay. Không
dùng số này. Vì vậy:

| | Giá gốc | Giá bán |
|---|---|---|
| Lúc nhập từ KCS | **0 đ**, nhãn "chưa có giá gốc" | Lấy từ đơn: thành tiền chưa VAT ÷ SL, tròn tới đồng. Cụm: Σ thành tiền các dòng trong cụm ÷ SL cụm |
| Ai sửa | Kế toán kho nhập tay sau, khi đã biết giá | Không sửa — đơn đã chốt thì giá bán đã đông cứng |
| Nằm ở đâu | Ô giá sẵn có của kho: `don_gia` dòng yêu cầu → `don_gia` dòng phiếu nhập → `don_gia_nhap` của lô | Cột mới `stock_request_lines.don_gia_ban` (BIGINT, nullable), chỉ điền cho yêu cầu nhập từ KCS |
| Dùng cho | Mọi con số tiền của kho: giá trị nhập / xuất / tồn, báo cáo Nhập–Xuất–Tồn | Hiện để tham khảo: "tồn này bán ra đáng bao nhiêu" |

Ví dụ dòng #8 "Hộp bánh mang đi 4 ngăn", 10.000 hộp, thành tiền 32.054.645 đ: lô vào với giá gốc 0 đ,
giá bán 3.205 đ/hộp. Giá bán **không** đặt ở danh mục, vì cùng một mã bán cho nhiều đơn với giá khác
nhau (TP-00007 trên DB dev có bốn giá: 3.109 / 3.205 / 2.970 / 2.912 đ/hộp).

**Kho là danh mục động — mọi thông tin gốc phải đi theo LÔ, không theo kho.**

Kho do người dùng tự khai ở Cấu hình danh mục, mỗi kho tự hiện thành một mục dưới "Kho hàng" (DB dev
đang có Kho Giấy, Kho Mực & Hóa chất, Kho Vật tư đóng gói…; chưa có kho thành phẩm nào). Hệ quả cho
thiết kế:

- **Không có "kho thành phẩm" cố định.** Yêu cầu nhập từ KCS để trống kho; thủ kho chọn kho lúc lập
  phiếu nhập (ô kho bắt buộc, không đoán hộ), đúng như mọi yêu cầu nhập khác. Giao hàng cũng tự chọn
  kho xuất như hiện nay.
- **Hàng đi qua nhiều kho bằng Điều chuyển.** Điều chuyển hiện tạo lô MỚI ở kho đích và chỉ chép giá
  + hạn dùng (`stock_voucher_service.dieu_chuyen`). Lô mới không còn nối về yêu cầu nhập từ KCS, nên
  mất cả ba thứ: đơn/khách, giá bán, và không nhận giá gốc sửa sau.
- **Cách vá: mỗi lô nhớ LÔ GỐC.** Lô nhập từ yêu cầu để `lo_goc_id` trống (chính nó là gốc). Điều
  chuyển ghi `lo_goc_id` của lô nguồn (hoặc id lô nguồn nếu nó là gốc) lên dòng phiếu nhập đích, ghi sổ
  chép sang lô mới. Chuyển tiếp A → B → C vẫn trỏ về một lô gốc. Áp cho mọi mặt hàng, không riêng
  thành phẩm.
- Đơn/khách và giá bán luôn đọc ở **lô gốc** (lô gốc → phiếu nhập → dòng yêu cầu). Không chép hai thứ
  đó qua mỗi lần điều chuyển.

**Sửa giá gốc sau khi ghi sổ** (việc mới — kho hiện chưa có đường sửa giá lô đã ghi sổ):

- Kế toán kho sửa **một lần trên lô gốc**. Danh sách "Thành phẩm chưa có giá gốc" đặt ở Báo cáo kho,
  gom **mọi kho** và chỉ hiện lô gốc — số kho thay đổi theo danh mục, bắt kế toán đi từng mục kho là
  sót. Gõ theo đơn vị của phiếu nhập (đ/hộp).
- Hệ ghi cho lô gốc **và mọi lô có `lo_goc_id` trỏ về nó**, ở bất kỳ kho nào: dòng phiếu nhập
  (`don_gia`, báo cáo Nhập–Xuất–Tồn đọc ở đây) và lô (`don_gia_nhap`, quy về đơn vị gốc như lúc ghi sổ;
  phiếu xuất đọc giá lô trực tiếp). Tất cả trong một giao dịch, lệch một ô là báo cáo và phiếu xuất
  ra hai số khác nhau.
- Có một lô trong nhóm đó nằm ở kỳ đã khoá sổ của kho nó thì chặn cả lần sửa
  (`_assert_period_open` theo kho + ngày của từng lô), báo rõ kho nào kỳ nào.
- Ghi vết ai sửa, lúc nào, giá cũ → giá mới.
- Chỉ áp cho lô gốc là thành phẩm nhập từ KCS. Giấy, vật tư vẫn giữ luật "kho không sửa giá".

**Hệ quả, ghi rõ để không ai đọc nhầm số:**

- Khi chưa nhập giá gốc, giá trị thành phẩm trên mọi báo cáo kho là **0 đ** (thiếu, không thổi phồng).
  Nhãn "chưa có giá gốc" cho biết số đó chưa đủ.
- Nhập giá gốc xong thì báo cáo tự đúng lại: báo cáo tính lúc mở và phiếu xuất đọc giá lô trực tiếp,
  nên phiếu xuất đã ghi sổ trước đó cũng ra giá trị mới. Không phải làm lại phiếu nào.
- Giá bán không đi vào báo cáo Nhập–Xuất–Tồn. Doanh thu vẫn nằm ở đơn hàng; lãi gộp = doanh thu − giá
  trị xuất kho, chỉ có nghĩa sau khi đã nhập giá gốc.

## 6. Những chỗ đọc ngược (thay cho sổ riêng)

| Chỗ | Nay đọc | Đổi thành |
|---|---|---|
| Nút + trạng thái trên màn KCS (`KcsChuoiCongDoan`) | `nhap_kho_yc` theo lần kiểm | Yêu cầu có `san_xuat_cong_viec_id` = công đoạn: mã DNN, đề nghị / kho đã nhận, trạng thái; bấm mã mở Yêu cầu nhập xuất |
| `kcs_bao_cao._trang_thai_gui_kho` | `SanXuatNhapKhoYc` | Cùng nguồn: chưa gửi / đang chờ kho / đã nhập đủ |
| `lenh_sx/boi_canh` + `trang_thai` (tab "Chờ nhập kho", "Sẵn sàng giao") | Đi vòng qua nhóm | Dòng yêu cầu `lsx_id` = lệnh → **neo thẳng lệnh**, bỏ vòng qua nhóm |
| Hồ sơ lệnh · khối Kho (`LenhSxHoSoView`) | Yêu cầu + lot "Đã nhận/Chưa nhận" | Các dòng yêu cầu của lệnh: mã DNN · đề nghị · kho đã nhận · kho nhận |
| Hồ sơ lệnh · khối Giao hàng (`ton_kha_dung_thanh_pham`) | Lot sản xuất − đã giao; chỉ tính trần khi nhóm 1-1-1 | Mỗi dòng đơn của nhóm: món `TP-…` · **tồn thật theo kho** (`on_hand_by_kho`) · trần = min(tồn thật ở kho đó, còn phải giao của dòng đơn). Cùng hai con số mà Giao hàng và kho tự kiểm, nên ba bên không vênh. Bỏ nhánh 1-1-1. |
| `KcsChotNhom` (danh sách lot "đã vào sổ / chờ kho nhận") | `san_xuat_kho_lot` | Dòng yêu cầu của nhóm |

Đóng nhóm (`dong_nhom`) **không đổi**: nó chỉ so số KCS đạt với Σ `so_luong_ra` của công đoạn cuối,
không đọc sổ kho nào.

### Một mã dùng chung cho nhiều đơn — tách bằng LÔ, không tách mã

Danh mục Thành phẩm gộp trùng theo tên đã chuẩn hoá (chốt 21/08/2026). Trên DB dev, TP-00007 "Hộp
bánh mang đi 4 ngăn" đang dùng cho 4 dòng đơn thuộc đơn 3 và đơn 4. Giữ một mã để danh mục không
phình, nhưng hàng của đơn nào phải giao cho đúng đơn đó:

- **Mỗi lô nhớ nguồn**: lô → lô gốc (§5, sống qua điều chuyển giữa các kho) → phiếu nhập → dòng
  yêu cầu `lsx_id` → lệnh → đơn → khách.
- Kho lập phiếu xuất cho Giao hàng đơn X:
  - hệ **gợi ý lô của chính đơn X trước**, rồi mới tới FEFO/FIFO như hiện nay;
  - chọn lô của **đơn khác cùng khách** (vd dùng hàng dư đơn cũ): cho phép, hiện cảnh báo *"Lô này
    sản xuất cho đơn DH003"*;
  - chọn lô của **khách khác**: chặn, vì cùng tên nhưng có thể khác file in.
- Màn Tồn kho vẫn hiện một dòng cho mã; mở chi tiết thì thấy từng lô kèm đơn/khách.

Nhờ vậy `spec-thuc-hien-san-xuat.md` §14.1 ("thành phẩm chỉ giao cho đúng đơn") vẫn đúng mà không
phải bỏ quyết định gộp mã theo tên. §14.1 sẽ ghi chú lại cách làm này.

## 7. BTP

Ngoài phạm vi: BTP đã gỡ hẳn khỏi sản xuất ngày 17/09/2026 (mg `0308`), nên thiết kế này chỉ nhập
thành phẩm.

## 8. Quyền

- **Tạo yêu cầu:** giữ cổng như nay — người thuộc tổ KCS (`gate_kcs`).
  Service gọi thẳng `StockRequestService.create` (như Giao hàng), nên người KCS **không** cần ô
  `kho:create`.
- **Nhận hàng:** quyền sẵn có của Hộp yêu cầu. Thủ kho / Quản lý kho không còn cần dòng quyền tổ
  SX để vào bàn tổ. Gỡ hai dòng đó trên DB dev hay không là việc của chủ dự án; code không phụ
  thuộc.
- **Sửa giá gốc, xem giá gốc / giá bán:** tái dùng quyền sẵn có "xem giá vốn" của Kho
  (`kho:view_cost`, seed đang cấp cho Kế toán kho). Thủ kho không có quyền này thì không thấy cả hai
  giá, đúng như kho đang ẩn giá hôm nay. Không đẻ quyền mới.
- Người KCS thấy yêu cầu mình tạo trong "Yêu cầu nhập xuất" theo phạm vi đang có (cây phòng ban).
  Tổ trưởng KCS trên DB dev có `kho:read`. Lúc làm phải kiểm lại một người KCS **không** giữ
  `kho:read` thì thấy gì. Nếu không thấy thì màn KCS vẫn hiện mã DNN và trạng thái, đủ để theo dõi.

## 9. Gỡ

- Backend:
  - endpoint `GET /api/san-xuat/kho/hop-thu`, `GET /kho/nhom/{id}`, `POST /kho/yeu-cau/{id}/xac-nhan`;
  - trong `services/san_xuat/kho.py`: `kho_xac_nhan_nhap`, `hop_thu_kho`, `chi_tiet_kho_nhom`,
    `_trang_thai_yc`, `_nhan_theo_yc`, `_yc_ra`, `_lot_ra`, `_get_or_create_hang`, `_tao_yc_tu_batch`
    (`tao_yeu_cau_nhap_kho_cong_doan` viết lại, `ton_kha_dung_thanh_pham` đổi theo §6);
  - `san_xuat_kho_repo` và model `san_xuat_kho` (3 bảng), schema tương ứng, hằng `YC_*`.
- Frontend:
  - phần Kho của `ThsxHopThuBar` trong `ThsxG5.tsx` (`KhoNhapHopThuRow`, dòng "Chỉ nhân viên kho
    mới xác nhận nhập.");
  - effect nạp hộp thư kho, `canKhoRead` / `canKhoCreate` ở `ThucHienSxPage`;
  - hàm client `khoHopThu`, `khoXacNhanNhap`, `khoChiTietNhom` và type đi kèm.
- Migration drop ba bảng ở §5 và cập nhật `docs/DB_SCHEMA.md`.
- Tài liệu: ghi chú lại `spec-thuc-hien-san-xuat.md` §14, `design-kcs-theo-lenh.md` §6.

## 10. Real-time

- **Tạo yêu cầu → kho:** chuông + SSE `stock_request_pending_changed`, sẵn có.
- **Kho ghi sổ → người KCS:** thông báo "cấp một phần / hoàn tất" gửi người tạo, sẵn có.
- **Thêm:** sau `svc.post` ở `kho_voucher.post_voucher`, nếu yêu cầu có `san_xuat_cong_viec_id`
  thì phát sự kiện sản xuất (khuôn `_phat_sse_kho`). Nhờ vậy màn KCS và hồ sơ lệnh tự cập nhật "kho
  đã nhận" mà không phải tải lại. Hook này chỉ đẩy tin, không ghi dữ liệu. Làm cùng khuôn với móc
  `delivery_notify` đang gọi ở bước lập phiếu.

## 11. Đối chiếu Print MIS

Business Central / PrintVis ghi sản lượng lệnh sản xuất bằng *Output Journal*: sản lượng cuối đổ
vào **item ledger của chính mặt hàng**, không vào sổ riêng của xưởng. Kho dùng put-away thì nhận
bằng chứng từ kho (*Inbound/Put-away*) rồi mới ghi sổ. Thiết kế này khớp khuôn đó: yêu cầu NHẬP
đóng vai chứng từ kho, phiếu nhập đóng vai ghi sổ, còn món `TP-…` là mặt hàng của lệnh. Khác biệt
là giá thành: BC tính giá vốn thực tế khi đóng lệnh. Ở đây phần mềm không tính được giá gốc, nên
lô vào 0 đ để kế toán kho nhập sau, kèm giá bán của đơn để tham khảo (§5).

## 12. Thứ tự làm

0. **BE — thành phẩm theo cụm (§3):**
   - `khai_cho_don` khai theo cụm bán, cùng luật `gop-nhom.ts` (nhãn + SL), viết lại một bản phía
     server kèm test đối chiếu;
   - Giao hàng chọn cụm, ghi đã giao cho mọi dòng của cụm, xuất kho một dòng.
1. **BE:**
   - cột `san_xuat_cong_viec_id` (+ `_HEADER_FIELDS`) và `stock_request_lines.don_gia_ban`
     (migration + DB_SCHEMA);
   - viết lại `tao_yeu_cau_nhap_kho_cong_doan`: chọn mã theo §3, trần theo §4, giá gốc 0, giá bán
     = thành tiền ÷ SL theo §5, `create(commit=False)`;
   - test: dòng đơn lẻ, cụm Ruột + Bìa (giá bán cụm), nhóm chứa hai cụm, đơn vị lệch / chưa khai,
     dòng chưa có thành tiền, bấm đúp, kho huỷ trả số về, chốt thiếu trả số về.
1c. **BE — lô gốc (§5):** cột `lo_goc_id` trên lô + dòng phiếu nhập; `dieu_chuyen` ghi lô gốc lên
    dòng phiếu nhập đích, ghi sổ chép sang lô. Test: A → B → C vẫn trỏ về một lô gốc; lô ở kho đích
    đọc ra đúng đơn/khách và giá bán.
1d. **BE + FE — sửa giá gốc (§5):** sửa trên lô gốc, lan sang mọi lô con ở mọi kho, dòng phiếu nhập +
    lô trong một giao dịch; chặn nếu một lô bất kỳ nằm ở kỳ đã khoá; chặn lô không phải thành phẩm
    từ KCS; ghi vết; danh sách "Thành phẩm chưa có giá gốc" (mọi kho) ở Báo cáo kho. Test: sửa xong
    báo cáo Nhập–Xuất–Tồn và giá trị phiếu xuất đã ghi sổ đều ra số mới, kể cả lô đã điều chuyển
    sang kho khác; kỳ khoá ở kho đích cũng chặn; người thiếu `kho:view_cost` bị chặn.
1b. **BE + FE — lô theo đơn (§6):** gợi ý lô của đúng đơn khi xuất cho Giao hàng, cảnh báo lô đơn
    khác cùng khách, chặn lô khác khách; chi tiết tồn hiện đơn/khách của lô.
2. **BE:** đổi các chỗ đọc ở §6 (`boi_canh`, `trang_thai`, `ho_so` khối Kho + Giao hàng,
   `kcs_bao_cao`), kèm test của từng chỗ.
3. **BE:** hook SSE §10.
4. **BE:** gỡ §9, migration drop ba bảng; chạy pytest nhắm các file `san_xuat_kho`, `kcs`, `lenh_sx`,
   `stock_request`, `delivery`.
5. **FE:** màn KCS (trạng thái + mã DNN), hồ sơ lệnh (khối Kho, Giao hàng), `KcsChotNhom`; nhãn
   "chưa có giá gốc" + cột giá bán cho lô thành phẩm; gỡ phần Kho khỏi bàn tổ; `npx tsc`.
6. **Xác minh bằng dev-browser, thao tác thật:**
   1. tt_kcs kiểm công đoạn cuối, bấm "Tạo yêu cầu nhập kho", thấy mã DNN;
   2. mở Yêu cầu nhập xuất, thấy yêu cầu đó;
   3. thủ kho mở Hộp yêu cầu, lập phiếu nhập một phần, chọn kho, ghi sổ;
   4. màn KCS và hồ sơ lệnh tự hiện "kho đã nhận" (không tải lại);
   5. Tồn kho hiện món `TP-…`, lô ghi "chưa có giá gốc" và giá bán lấy từ đơn;
   6. Giao hàng gửi yêu cầu xuất, kho xuất được;
   7. điều chuyển một phần lô sang kho khác; lô bên kho đích vẫn hiện đơn/khách, giá bán;
   8. kế toán kho mở Báo cáo kho ▸ "Thành phẩm chưa có giá gốc", gõ giá gốc; báo cáo Nhập–Xuất–Tồn
      của cả hai kho ra giá trị mới;
   9. bàn tổ Tổ in không còn thanh "Kho chờ xác nhận".
