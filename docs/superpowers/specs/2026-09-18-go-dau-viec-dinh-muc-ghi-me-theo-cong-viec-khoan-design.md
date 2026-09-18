# Gỡ đầu việc định mức · Vật tư theo công đoạn · Ghi mẻ theo công việc khoán · Sản xuất thôi chia — Thiết kế

**Ngày chốt:** 18/09/2026
**Phạm vi (7 module):** Danh mục Công đoạn · Danh mục Công việc khoán · Kế hoạch SX (Lệnh) ·
Bài ghép · Thực hiện SX (bàn tổ) · Xếp lịch · Bảng lương.

---

## 0. CÁC ĐIỂM PHỤ — 16 ĐIỂM, ĐÃ CHỐT HẾT 18/09/2026

Các điểm chủ dự án chưa nói trong yêu cầu gốc; tôi nêu, chủ dự án đã duyệt từng mục.

**Nhóm A — buộc phải quyết, vì gỡ cái được chỉ thì nó rụng theo:**

1. Hai cột chép năng suất trên bước lệnh (`nang_suat`, `don_vi_nang_suat`) → **gỡ**. Chúng chép từ
   đầu việc; đầu việc đi thì chúng thành số mồ côi không ai ghi.
2. Cách đo giờ chạy của đầu việc (`cong_thuc_gio`) → **gỡ, không dời** về công việc khoán. Bước tổ
   nay gõ giờ tay nên không còn ai đọc nó.
3. Chặn xoá công việc khoán → đổi căn cứ từ *"công đoạn đang khai việc này"* sang *"tổ đã ghi N mẻ
   bằng việc này"*. Vẫn chặn, chỉ khác chỗ đếm.
4. **Cột Khoán của bảng lương GIỮ NGUYÊN** — *"cứ để đó sau này sẽ dùng"*. Cả cột lẫn ống nối
   (`PieceWorkService.khoan_map` / `defect_map`) đứng y chỗ, vẫn trả 0 như từ 11/09. Chỉ gỡ đúng
   cái **nguồn đã chết**: `production_output_repo` đọc bốn bảng phân bổ sắp xoá. Màn "Khoán theo kỳ"
   sau này cắm nguồn mới vào đúng ống nối đó, không phải dựng lại cột.
5. Bước tổ mất dải min/TB/max → chỉ còn một số nhập tay, râu Gantt của bước tổ mất.
6. Mô tả quyền "Xác nhận sản lượng" rút lại còn bàn giao/nhận + hỗ trợ chéo (bỏ chia/chốt/bù trừ).

**Nhóm B — đã chốt theo quyết định của chủ dự án:**

7. **Mẻ có CHỦ duy nhất** (tổ của bước), nhưng **hiện ở tab Sản lượng của mọi tổ có người trong
   mẻ — cùng một con số, không chia.** Tổ khách thấy mẻ ở mục riêng, không cộng vào tổng của mình.
   Bỏ ô tỷ lệ phần trăm, giữ phiếu "ai sang giúp ai". Chi tiết §7.3b.
8. **Mẻ CHỤP đơn giá** (tên + đơn vị + đơn giá). Danh mục đổi giá về sau thì mẻ hiện băng *"Danh
   mục đã đổi"* kèm nút đồng ý, y khuôn băng đang chạy dưới chân lệnh. Chi tiết §7.2.
9. **Chặn ở cổng lập kế hoạch, không chặn ở bàn tổ.** Bước giao cho tổ chưa khai công việc khoán
   nào ⇒ tính là một mục thiếu, nút *"Sẵn sàng lập kế hoạch"* không bấm được. Xuống bàn tổ thì luôn
   có việc để chọn nên ô chọn việc khoán là **bắt buộc**. Chi tiết §5.4.
10. Ô tìm việc khoán **hiện cho mọi tổ**, kể cả tổ có 1 việc.
11. Việc phát sinh **không sinh tiền ở đây, chỉ ghi nhận** — *"chỉ cần ghi nhận thay 2 bản kẽm
    thôi"*. Không công thức, không phép nhân nào ở tầng sản xuất.
12. Hai khoá số người chỉ để hiển thị ở Xếp lịch (`so_nguoi_tong`, `so_nguoi_chuan`) → **gỡ cho
    sạch**.
13. Màn thợ hiện **danh sách người tham gia mẻ**, **không** hiện số phút của ai. Chi tiết §7.5.
14. Ô "Số giờ kế hoạch": ô **số**, không nhận chữ, **không bắt tròn** — gõ 4,5 giờ được.
15. Vật tư của công đoạn: **một vật tư chỉ khai một lần**; lúc chép dữ liệu cũ, trùng thì giữ dòng
    khai trước.
16. Luật *"phải có ít nhất 1 thợ mới bắt đầu được việc"* → **giữ**. Đó là luật về người, không phải
    về kíp.

## 1. Quyết định gốc của chủ dự án

> *"Bỏ đầu việc định mức và tổ cho công đoạn"* — sau khi soi ảnh chốt lại: **"đầu việc và định mức
> của tổ"** là tên NGUYÊN MỘT KHỐI trong drawer Công đoạn, không phải hai thứ. Khối "Phòng ban /
> Tổ phụ trách" **không** bị bỏ: *"tôi kêu bỏ bước tổ lúc nào"*.
>
> *"Thêm tab vật tư để chọn nhiều vật tư và thiết công thức định mức cho từng vật tư."*
>
> *"Ở module công việc khoán thêm tab công thức khoán."*
>
> *"Bỏ công việc chi tiết và kíp dưới LSX"* — tức hai ô **Kíp chuẩn** và **Đầu việc thợ làm** ở
> drawer bước. *"Vật tư được bung theo công đoạn."*
>
> *"Chọn loại bước là tổ thì phải nhập thời gian ước lượng của tổ và để mặc định là 0"* · *"bản
> chất nó là số giờ kế hoạch, nên sửa nhãn luôn; nếu thiếu thì cứ để 0"* · *"không cần cảnh báo"*.
>
> *"Dưới sản xuất sẽ xuất hiện tất cả các công việc khoán ở tổ đó, chỉ chọn được một trong đó,
> nhập số lượng cho công việc đó — nó là ghi mẻ đó nhưng cho công việc chứ không phải công đoạn
> nữa. Phải hiển thị cả đơn giá, đơn vị tính, ghi chú và danh sách việc phát sinh của việc đó. Có
> thể chọn một hoặc nhiều việc phát sinh rồi nhập số lượng"* — mỗi việc phát sinh hiện **tên + đơn
> giá + đơn vị tính**.
>
> *"Việc phát sinh như lên khuôn không cộng vào sản lượng."*
>
> *"Không có cái nào là chia cho từng người đâu. Ví dụ mẻ đó 3 người, ghi sản lượng 3.000 và thay
> kẽm số lượng 2, thì ghi nhận thế thôi, đừng có chia bất cứ gì."*
>
> *"SẢN XUẤT CHỈ GHI NHẬN SỐ LƯỢNG — nó không được tự động nhân chia cộng trừ gì đó để ra tiền."*
> Cách chia sẽ có **khi sang màn kế toán**.
>
> *"Bỏ luôn logic kíp người, và mấy cái chặn hoặc cảnh báo hoặc phép tính liên quan đến kíp người."*
>
> *"Sửa cả bên bài ghép như bên lệnh."*

## 2. Ba nguyên tắc

**1. Sản xuất chỉ GHI NHẬN.** Không phép nhân, chia, cộng, trừ nào ở tầng sản xuất. Không chia sản
lượng cho người, không quy đổi đơn vị, không ra tiền. Đơn giá / ĐVT / ghi chú bày ở bàn tổ chỉ để
thợ nhận ra đúng việc mình vừa làm.

**2. Số lượng ghi mẻ không phải thừa số của đơn giá.** Cán màng đơn giá 1.500 đ/m² mà mẻ ghi 5.000
tờ — hai đơn vị khác nhau, và **không ai được tự quy đổi ở đây**. Công thức khoán khai ở danh mục
là để **màn kế toán sau này** dùng; tầng sản xuất tuyệt đối không chạy nó.

**3. Công đoạn là CÔNG NGHỆ, công việc khoán là VIỆC CỦA TỔ.** Hôm nay `cong_doan_dau_viec` là giao
điểm của hai thứ đó — bản này cắt giao điểm, mỗi bên tự đứng. Còn **tổ** thì vẫn thuộc công đoạn:
"cán màng mờ do Tổ cán phủ + Tổ thành phẩm làm" là tri thức công nghệ, không phải việc khoán.

## 3. Module **Danh mục Công đoạn**

| | |
|---|---|
| **Thêm** | Tab khai báo thứ hai **"Vật tư"** — bảng nhiều dòng: Mã · Tên · ĐVT · **Công thức định mức**. Bảng mới `cong_doan_vat_tu`. |
| **Bớt** | Cả khối **"Đầu việc và định mức của tổ"** (vùng khoanh đỏ trong ảnh chốt): dòng chọn đầu việc, hai cột chiếu Đơn giá khoán (ĐVT + đơn giá), Năng suất khoán tối thiểu/trung bình/tối đa + đơn vị, Kíp chuẩn (người), cột Công thức tiền công, và bảng con Vật tư của đầu việc. Bảng `cong_doan_dau_viec` + `cong_doan_dau_viec_vat_tu` XOÁ. |
| **Không đụng** | **"Phòng ban / Tổ phụ trách"** (nhiều tổ, tổ đầu là mặc định) · "Máy làm được công đoạn này" · "Máy chạy được công đoạn này" (tốc độ, canh máy, cách đo giờ chạy) · đơn vị vào/ra · bù hao · công thức tính giá · công thức sản lượng ra · mã/tên/giai đoạn/ghi chú. |

### 3.1 Bảng `cong_doan_vat_tu`

| Cột | Kiểu | Vai |
|---|---|---|
| `id` | int PK | |
| `cong_doan_id` | int FK CASCADE | |
| `vat_tu_id` | int, soft-ref `vat_tu_in_an` | service chặn id lạ / đã ngừng dùng |
| `thu_tu` | int | thứ tự người khai |
| `cong_thuc_luong` | Text nullable | ĐỊNH MỨC — ra LƯỢNG theo ĐVT của vật tư |

Unique `(cong_doan_id, vat_tu_id)`. **Không có cột số lượng chết** — lý do giữ nguyên từ bảng cũ:
định mức tuỳ quy cách từng lệnh nên khai công thức chứ không khai con số. Trống công thức ⇒ bước
lệnh không bung dòng đó, kèm câu lý do, không đoán.

Tab riêng chứ không nhét thêm group vào tab "Khai báo thông tin": bảng nhiều dòng × 4 cột không
đứng chung với các ô đơn lẻ.

### 3.2 Backfill

Gộp `cong_doan_dau_viec_vat_tu` lên theo `cong_doan_id`; trùng `vat_tu_id` giữ dòng `thu_tu` nhỏ
nhất. Đo trên DB dev 18/09/2026: 7 dòng vật tư, **0 trường hợp** một công đoạn có cùng vật tư ở hai
đầu việc với hai công thức khác nhau ⇒ gộp là union sạch.

**Mất dữ liệu:** năng suất khoán (min/TB/max + đơn vị), kíp chuẩn, cách đo giờ chạy của đầu việc
trên 27 dòng định mức. Không khôi phục sau migration. `seed_luong_ban_sx.py` phải gỡ phần seed định
mức đầu việc.

## 4. Module **Danh mục Công việc khoán**

| | |
|---|---|
| **Thêm** | Tab **"Công thức khoán"** → cột mới `piece_rates.cong_thuc_khoan` (Text). Ra **LƯỢNG** theo `piece_rates.unit`; **không ai chạy nó ở tầng sản xuất** — để dành cho màn Khoán theo kỳ. Ô tìm **tương đối** trong danh sách (bỏ dấu + khớp một phần: `can mang` và `màng` đều ra "Cán màng mờ"). |
| **Bớt** | — |
| **Không đụng** | Mã (tự sinh `KH-`) · Tên · Tổ làm việc này (nhiều tổ) · Đơn vị tính khoán · Đơn giá · Ghi chú · Việc phát sinh (tên + đơn giá + đơn vị) · nhập/xuất Excel. |

**Backfill** `cong_thuc_khoan` từ `cong_doan_dau_viec.cong_thuc_khoan`. Đo trên DB dev: mỗi công
việc khoán chỉ khai ở **đúng một** công đoạn ⇒ 1-1, không công thức nào phải bỏ.

Đây là **quay ngược mg `0274`**, ghi rõ để lượt sau không tưởng là quên: hồi đó dời công thức xuống
`cong_doan_dau_viec` vì "cùng đầu việc làm ở hai công đoạn thì đếm khác nhau". Lý do ấy tan khi mỗi
công việc khoán đã mang **mã riêng của xưởng** đã mã hoá sẵn khổ / số màu / số lớp. Một mã việc =
một cách đếm.

`cong_thuc_gio` (cách đo giờ chạy của đầu việc) **không** dời về đây: bước tổ thôi tính giờ tự động
(§5), nên không còn ai đọc nó. Gỡ cùng bảng.

**Việc phát sinh** mở đường xuống sản xuất (§7). Không có công thức — tiền của nó là *số lượng ×
đơn giá*, và phép nhân đó xảy ra ở **màn kế toán**, không ở bàn tổ.

## 5. Module **Kế hoạch SX (Lệnh)**

| | |
|---|---|
| **Thêm** | Bước loại **Tổ**: ô **"Số giờ kế hoạch"** (giờ), cột `lsx_cong_doan.so_gio_ke_hoach`, `Numeric(8,2)` NOT NULL **mặc định 0**. Thiếu thì để 0 — **không cảnh báo, không chặn**. |
| **Bớt** | Ô **Kíp chuẩn** (`so_nhan_cong_tieu_chuan`) · ô **Đầu việc thợ làm** (`khoan_json` + endpoint `dau-viec-options`) · hai cột chép năng suất (`nang_suat`, `don_vi_nang_suat`) · câu ghi chú dưới ô Tổ *"Đổi tổ thì đầu việc khoán nạp lại theo tổ"*. |
| **Không đụng** | Ô **Tổ phụ trách** — giữ nguyên hình, giữ nguyên nguồn options (chỉ các tổ đã khai ở công đoạn, tổ đầu là mặc định) · máy · khuôn · số lượng vào/ra · hao hụt · phụ thuộc DAG · gia công ngoài · đính kèm. |

### 5.1 Thời lượng bước

`thoi_luong_buoc` đổi đúng một nhánh:

- **bước Tổ** → `so_gio_ke_hoach × 60` phút. Hết. Không chia kíp, không quy đổi đơn vị, không đọc
  năng suất. `so_gio_ke_hoach = 0` ⇒ 0 phút, im lặng.
- **bước Máy / Thuê ngoài** → **không đổi một dòng nào**: `phat_sinh_phut + makeready + SL × 60 ÷
  tốc_độ_máy × số_lượt`, đọc sống danh mục Máy.

Đi theo nhánh bước tổ: `dich_gio_cua_khoan()` XOÁ HÀM; `sl_tinh_cua_buoc()` bỏ nhánh quy đổi SL về
đơn vị năng suất của bước tổ (phút gõ tay không cần quy đổi). Ba khoá `nguon_nang_suat` ·
`nang_suat_co_so` · `nang_suat_hieu_dung` trong payload bước chỉ còn nghĩa cho bước máy; bước tổ trả
`null` và `phuong_phap = "to_gio_tay"`. Mã cảnh báo `thieu_nang_suat` của bước tổ XOÁ (không cảnh
báo nữa).

Dải min/TB/max của bước tổ co về một điểm — chỉ còn một số nhập tay. Râu Gantt của bước tổ mất.

### 5.2 Vật tư bung theo công đoạn

`_vat_tu_bung` đổi nguồn: đọc `cong_doan.vat_tus` thay vì vật tư của đầu việc. **Đơn giản hơn hiện
tại** — hôm nay nó phải đợi bước đã chọn đầu việc mới bung được; nay mọi bước có công đoạn là bung
được ngay lúc tạo lệnh, kể cả bước máy.

`_goi_y_luong_vat_tu` đổi nguồn theo. Endpoint `GET /api/lsx/{id}/dau-viec-options` XOÁ; phần
`vat_tus` / `canh_bao_vat_tu` của nó chuyển sang `GET /api/lsx/{id}/xem-truoc-buoc`.

MRP (`ke_hoach_vat_tu_service`) không phải sửa: nguồn nhu cầu của nó vẫn là `lsx_cong_doan_vat_tu`
đã ghim.

### 5.3 Chặn xoá công việc khoán — đổi lý do

Hôm nay: *"không xoá được, công đoạn Ghi kẽm CTP đang khai việc này"*. Sau bản này không công đoạn
nào khai nữa, nên đổi thành: *"không xoá được, Tổ cán phủ đã ghi 12 mẻ bằng việc này"* — đếm
`san_xuat_batch.piece_rate_id`. Vẫn chặn, chỉ khác căn cứ. Đúng hơn bản cũ: mẻ đã ghi là vết thật,
ảnh chụp trên bước chỉ là dự kiến.

### 5.4 Cổng "Sẵn sàng lập kế hoạch" — thêm một mục thiếu

Mã mới trong checklist chặn (`thieu_cua`): **`thieu_viec_khoan_to`** — *"Bước Cán màng mờ giao cho
Tổ cán phủ mà tổ này chưa khai công việc khoán nào"*. Nhãn khai ở `LSX_THIEU_LABELS` như 6 mã đang
có; cách chặn y hệt `thieu_to_may` / `thieu_khuon`.

Soi mọi bước loại **Tổ** đã chọn tổ; tổ nào không có dòng nào trong `cong_viec_khoan_to` với
`active = true` thì thêm mã. Soi cả bước **Máy** (sửa lúc làm, 18/09/2026): tổ đứng máy cũng ghi
mẻ ở bàn tổ — ví dụ §7.1 "Bình bài & ra kẽm" chính là việc của máy CTP — nên miễn bước máy là để
tổ In kẹt không ghi nổi mẻ. Chỉ bước **Thuê ngoài** miễn, và mẻ của nó không bắt việc khoán.

**Vì sao chặn ở đây mà không chặn ở bàn tổ:** thợ đứng máy không sửa được danh mục. Bắt lỗi ở cổng
lập kế hoạch thì người lập kế hoạch thấy ngay lúc còn sửa được, còn nếu để xuống bàn tổ mới báo thì
tổ bị kẹt không ghi nổi mẻ giữa ca. Đổi lại: xuống bàn tổ thì **chắc chắn** tổ nào cũng có việc để
chọn, nên ô chọn việc khoán ở mẻ là **bắt buộc**, không có nhánh "để trống".

### 5.5 Băng "Danh mục đã đổi" dưới chân lệnh

Băng này hiện so **nội dung** ảnh chụp khoán của bước với danh mục hiện tại. Gỡ ảnh chụp khoán thì
nửa khoán của băng chết theo: `KHOAN_TRUONG` (6 ô: tên đầu việc, đơn vị, cách đo giờ, năng suất
người-giờ, đơn vị năng suất, kíp chuẩn) và hàm `khoan_lech` XOÁ.

Nửa **vật tư** của băng **GIỮ**, chỉ đổi nguồn dựng ảnh mới sang vật tư của công đoạn. Cách so vẫn
là so nội dung, **không** so mốc thời gian — lý do cũ còn nguyên giá trị: bảng con không có cột thời
gian, sửa con không chạm mốc của cha (đo thật 07/09/2026: thêm hai dòng vật tư cho CD-0012 mà mốc
vẫn đứng ở 20/08).

## 6. Module **Bài ghép**

Sửa **y hệt §5**, vì `bai_ghep_cong_doan` là bảng bước song sinh mang đúng các cột đó:

| | |
|---|---|
| **Thêm** | `bai_ghep_cong_doan.so_gio_ke_hoach` — cùng kiểu, cùng mặc định 0. |
| **Bớt** | `khoan_json` · `so_nhan_cong_tieu_chuan` · `nang_suat` · `don_vi_nang_suat` · ô Kíp chuẩn + ô Đầu việc trong form bước chung. |
| **Không đụng** | Sơ đồ ghép · bình bài · tổ · máy · toả sản lượng về từng lệnh (`san_xuat_ket_qua_nhanh`). |

## 7. Module **Thực hiện SX (bàn tổ)**

### 7.1 Ghi mẻ theo công việc khoán

| | |
|---|---|
| **Thêm** | Trong form Ghi mẻ: danh sách **công việc khoán của tổ đang mở bàn**, chọn **đúng một**; mỗi dòng hiện **đơn giá · ĐVT · ghi chú**. Dưới việc đang chọn: danh sách **việc phát sinh** của chính nó, tick một hoặc nhiều, mỗi cái một ô số lượng; mỗi dòng hiện **tên · đơn giá · ĐVT**. Ô tìm tương đối, **hiện cho mọi tổ**. |
| **Bớt** | Xem §7.3 (tầng chia) và §7.4 (kíp). |
| **Đổi** | Tab Sản lượng của tổ chia hai mục: **mẻ của tổ** (cộng vào tổng) và **người của tổ đi làm ở tổ khác** (không cộng). Mẻ luôn hiện đủ con số ở mọi tổ nhìn thấy nó (§7.3b). |
| **Không đụng** | Giờ bắt đầu – kết thúc · Tổng · Tốt · Hỏng (tự tính = Tổng − Tốt) · Mô tả lỗi · Ghi chú · lô đầu vào · bàn giao · KCS · tiến độ *đã làm / còn thiếu* · đóng nhóm đủ · nhập kho thành phẩm. |

Hình form:

```
Việc khoán của tổ                              [ô tìm — luôn hiện]
 ○ KH-0007  Bế hộp khổ nhỏ         120 đ / con     "chỉ hộp ≤ 20cm"
 ● KH-0013  Bình bài & ra kẽm   15.000 đ / bản kẽm
   └─ Việc phát sinh của KH-0013
      ☑ Thay kẽm             40.000 đ / bản    [ 2 ]
      ☐ Vệ sinh máy          30.000 đ / lần    [   ]
```

Danh sách = công việc khoán có tổ đang mở bàn trong `cong_viec_khoan_to`, `active = true`. Đo DB
dev: tổ đông nhất 17 việc, các tổ khác 1–6 ⇒ bày thẳng cả danh sách, và ô tìm **hiện cho mọi tổ**
kể cả tổ 1 việc (chốt ý 10 — nhất quán hơn là bày lắt nhắt theo số lượng). Tìm **tương đối**: bỏ
dấu + khớp một phần, gõ `binh bai` hay `kem` đều ra. Màn xưởng: nút to, số lớn, bấm cả dòng được.

**Không có ô thành tiền, không có số tiền nào.**

### 7.2 Dữ liệu mẻ

Cột mới `san_xuat_batch.piece_rate_id` — int, soft-ref `piece_rates`.

**Bắt buộc ở tầng service và form, KHÔNG phải NOT NULL ở DB.** Lý do: mẻ ghi trước bản này không có
việc khoán nào để backfill, ép NOT NULL là migration chết ngay trên DB dev đang có mẻ. Nên cột để
nullable cho mẻ cũ, còn mẻ **mới** thì service từ chối nếu thiếu. Cổng "Sẵn sàng lập kế hoạch"
(§5.4) đã chặn từ trước nên xuống bàn tổ tổ nào cũng có việc để chọn — không có nhánh "để trống".

Service chặn thêm: id lạ · việc không thuộc tổ của bước · `active = false`.

Bảng mới `san_xuat_batch_phat_sinh`:

| Cột | Kiểu | Vai |
|---|---|---|
| `id` | int PK | |
| `batch_id` | int FK `san_xuat_batch` CASCADE | |
| `phat_sinh_id` | int, soft-ref `cong_viec_khoan_phat_sinh` | |
| `so_luong` | `Numeric(14,3)` | |
| `ten_snapshot` · `don_vi_snapshot` · `don_gia_snapshot` | String · String · `Numeric(14,2)` | ảnh chụp lúc ghi mẻ |

Unique `(batch_id, phat_sinh_id)`. Service chặn `phat_sinh_id` không thuộc `piece_rate_id` của mẻ.

**Mẻ CHỤP đơn giá**, cả việc khoán lẫn việc phát sinh — chốt của chủ dự án, quay ngược đề xuất ban
đầu của tôi. Mẻ ghim thêm `ten_khoan_snapshot` · `don_vi_khoan_snapshot` · `don_gia_khoan_snapshot`
cho chính việc khoán đã chọn.

Ảnh chụp đây **không sinh tiền** — không ô thành tiền, không phép nhân nào ở bàn tổ. Nó chỉ trả lời
*"lúc ghi mẻ, việc này đang treo giá bao nhiêu"*, để tháng sau danh mục lên giá thì vẫn đọc lại
được mẻ đúng bối cảnh của nó.

### 7.2b Băng "Danh mục đã đổi" cho mẻ

Đi kèm ảnh chụp, y khuôn băng đang chạy dưới chân lệnh: mẻ dựng lại ảnh *"nếu ghi bây giờ"* rồi đối
chiếu với ảnh đang lưu, **so nội dung chứ không so mốc thời gian**.

```
⚠ Danh mục đã đổi so với lúc ghi mẻ
   Thay kẽm · đơn giá   40.000 → 45.000
   Bình bài & ra kẽm · đơn vị   bản kẽm → bản
                                    [ Cập nhật theo danh mục ]  [ Giữ số cũ ]
```

Bấm **Cập nhật** thì ảnh chụp của mẻ lấy số mới, ghi vết ai bấm lúc nào vào nhật ký. Không bấm thì
mẻ giữ số cũ vô hạn, băng vẫn treo đó — **hệ không bao giờ tự đổi số dưới chân mẻ đã ghi**.

Tái dùng đúng cơ chế so nội dung của `lsx_danh_muc_doi.py` (cùng hàm `_chuan` quy "chưa có gì" về
một dạng, cùng sai số `1e-9` cho số thực), chỉ thêm một bộ trường so cho mẻ. **Không** chép cách so
`updated_at` của băng báo giá — cùng lý do đã ghi ở §5.5.

Ba ô so của việc khoán: tên · đơn vị · đơn giá. Ba ô so của mỗi việc phát sinh: tên · đơn vị ·
đơn giá. Việc phát sinh bị **xoá khỏi danh mục** thì báo *"Thay kẽm — đã xoá khỏi danh mục"*, không
tự gỡ khỏi mẻ.

### 7.3 Gỡ TRỌN tầng chia sản lượng

Hôm nay mẻ 3.000 với 3 người bị máy tự chia 1.200 / 1.000 / 800 theo phút chấm công. Chủ xưởng bác:
*"ghi nhận thế thôi, đừng có chia bất cứ gì"*, và cách chia sẽ có ở màn kế toán.

| Gỡ | Cái gì |
|---|---|
| **Bảng** | `san_xuat_phan_bo` · `san_xuat_phan_bo_dong` · `san_xuat_phan_bo_bu_tru` · `san_xuat_phan_bo_loai_tru` — XOÁ BẢNG |
| **Cột** | `san_xuat_ho_tro.ty_le_phan_tram` — XOÁ CỘT (tỷ lệ chỉ để chia). Bảng `san_xuat_ho_tro` **giữ** làm vết "người tổ nào sang giúp tổ nào, ngày nào", kèm luồng hai bên xác nhận. Xem §7.3b — mẻ nhiều tổ nay hiện ở cả hai bên. |
| **Engine** | `services/san_xuat/phan_bo.py` — XOÁ FILE (`_tinh_batch`, `BoNhoTinhMe`, `_ghi_dong`, largest-remainder, trọng số theo phút) |
| **Repo** | `repositories/san_xuat_phan_bo_repo.py` — XOÁ FILE |
| **Endpoint** | `POST /outputs/{batch_id}/phan-bo` · `/phan-bo/{id}/chot` · `/mo-lai` · `/bu-tru` · `/loai-tru` · `/go-loai-tru` — XOÁ |
| **Mặt đọc** | khoá `chia_du_kien` trong chi tiết công việc (`board.py`) — XOÁ |
| **Frontend** | `PhanBoBlock` ("Chia sản lượng") · `BangChia` · `BuTruForm` và các nút Tính / Chốt / Mở lại / Bù trừ / Loại trừ — XOÁ |
| **Quyền** | Quyền chi tiết **"Xác nhận sản lượng"** rút lại còn: bàn giao / nhận, hỗ trợ chéo. Bỏ phần chia / chốt / mở lại / bù trừ / loại trừ khỏi mô tả quyền. |

**Mẻ sau bản này còn đúng:** giờ bắt đầu – kết thúc · việc khoán nào · sản lượng tốt / hỏng · mô tả
lỗi · **danh sách người tham gia** · việc phát sinh kèm số lượng · lô đầu vào · máy đã chạy · ca ·
sự cố dừng máy. Không con số nào bị nhân hay chia.

### 7.3b Mẻ có chủ duy nhất, nhưng hiện ở mọi tổ có người trong mẻ

**Chủ của mẻ là MỘT tổ, không bao giờ hai.** Chuỗi khai là *tổ → công đoạn → việc khoán → mẻ*: bước
giao cho tổ nào thì mẻ của bước đó thuộc tổ ấy, và việc khoán cũng chỉ chọn được trong danh sách
việc của chính tổ ấy. Chủ mẻ = `lsx_cong_doan.department_id` của bước, không cần cột mới.

Tổ khác có người trong mẻ thì **không phải đồng chủ** — họ là khách. Nên tab Sản lượng của tổ chia
hai mục:

```
Tab Sản lượng — Tổ cán phủ · tháng 9

MẺ CỦA TỔ
  18/09 · LSX26-0012 · Bình bài & ra kẽm · mẻ 1.000
        Người: c · a (tổ bế) · b (tổ bế)
  17/09 · LSX26-0009 · Cán màng mờ · mẻ 2.000
        Người: c · e
                                                    Tổng mẻ của tổ   3.000

NGƯỜI CỦA TỔ ĐI LÀM Ở TỔ KHÁC — không cộng vào tổng
  18/09 · LSX26-0031 · Bế hộp khổ nhỏ · mẻ 800 · chủ mẻ: Tổ bế
        Người của mình có mặt: d
```

Ba luật:

1. **Cùng một con số ở mọi tổ nhìn thấy nó.** Mẻ 1.000 thì tab tổ cán thấy 1.000, tab tổ bế cũng
   thấy 1.000 (ở mục khách). Không tổ nào thấy 400 hay 600. *"Ghi nhận thế thôi, đừng có chia bất
   cứ gì."*
2. **Đủ danh sách người**, ai không thuộc tổ đang xem thì kèm nhãn tổ gốc — để tổ trưởng biết ngay
   ai là người mình, ai sang giúp.
3. **Không có số phút của ai** (chốt ý 13).

**Dòng tổng cộng được, không sợ đếm hai lần** — vì chỉ cộng mục "MẺ CỦA TỔ", mà mỗi mẻ chỉ có một
chủ. Cộng tổng của cả 8 tổ ra đúng sản lượng xưởng, không mẻ nào bị tính hai lượt. Mục khách để
riêng, có câu *"không cộng vào tổng"* ngay trên đầu mục.

### 7.4 Gỡ TRỌN logic kíp

| Loại | Gỡ |
|---|---|
| **Cột** | `san_xuat_phien_chay.ly_do_so_nguoi` |
| **Chặn** | Bắt đầu việc đòi lý do khi số người thực tế khác dự kiến — XOÁ, bỏ cả ô chọn lý do trên màn |
| **Hiển thị** | `du_kien_so_nguoi` trên thẻ việc bàn tổ |
| **Giữ** | Luật *"roster phải có ≥ 1 thợ mới cho bắt đầu việc"* — đó là luật về người, không phải về kíp |

**Hệ quả nói trước:** hệ thôi biết một việc *nên* mấy người, nên tổ cử 1 người vào việc 5 người cũng
không ai cảnh báo. Đúng chủ trương "máy chỉ ghi nhận".

### 7.5 Màn của thợ đổi nghĩa

Mục *"Sản lượng của tôi"* hiện đọc dòng chia đã chốt — hết nguồn. Đổi thành **"Các mẻ tôi tham
gia"**: ngày · lệnh · công đoạn · việc khoán · sản lượng của **cả mẻ** · **danh sách người tham
gia**. Không có dòng "phần của tôi", **không có số phút của ai**.

```
18/09 · LSX26-0012 · Cán màng mờ
Bình bài & ra kẽm · mẻ 1.000 tờ
Người: tôi · a (tổ bế) · b (tổ bế)
```

Thợ vẫn xem lại được mình đã làm gì để đối chiếu với kế toán; hệ không bịa ra con số mà không ai
quyết. Endpoint `GET /api/san-xuat/toi/san-luong` đổi hình trả về, vẫn chỉ trả mẻ mà chính người
gọi có tham gia.

## 8. Module **Xếp lịch**

| | |
|---|---|
| **Thêm** | — |
| **Bớt** | `so_nguoi_tong` trên thẻ lệnh · `so_nguoi_chuan` trên dòng bước (cả hai chỉ là số hiển thị, không luật nào bám) |
| **Không đụng** | Đặt giờ bắt đầu → ra ngày kết thúc · mốc bước · máy · lịch làm việc · vấn đề / xung đột |

Bước tổ lấy thời lượng từ `so_gio_ke_hoach` (§5.1). Bước tổ để 0 giờ ⇒ chuỗi ngày kết thúc của lệnh
tính như bước đó dài 0 — **không cảnh báo**, theo đúng ý chủ dự án.

Detector "vượt quân số tổ" (`xep_lich_service.py` nhân *giờ × số người*) không phải xử riêng: nó là
ruột **Xếp lịch 2**, module đó đang được gỡ ở session khác. Bản này gọi module còn lại là **Xếp
lịch** và không sờ vào file của hai module đó ngoài hai khoá hiển thị ở trên.

## 9. Module **Bảng lương**

| | |
|---|---|
| **Thêm** | — |
| **Bớt** | Đúng **một** thứ: `repositories/production_output_repo.py` XOÁ FILE + gỡ wiring ở `deps.py`. File đó đọc bốn bảng phân bổ sắp bị xoá nên không xoá là vỡ import. |
| **Không đụng** | **Cột Khoán (`payroll_lines.khoan`) GIỮ NGUYÊN** — *"cứ để đó sau này sẽ dùng"*. Giữ luôn cả ống nối `PieceWorkService.khoan_map` / `defect_map` và ô Khoán trên màn lương. Vẫn trả **0** như từ 11/09. Cột `.thuong_to_truong` cũng không đụng. |

**Không đổi một đồng nào, và không gỡ một ô nào trên màn lương.** `production_output_repo` hiện trả
`unit_price = 0.0` cứng, nên `khoan_map` / `defect_map` đã luôn ra 0 từ 11/09/2026 — cái bị xoá là
**nguồn đã chết**, không phải cột lương.

`PieceWorkService` giữ nguyên với `outputs = None`; nó đã có nhánh trả rỗng nên chạy im. Ống nối
đứng sẵn ở đó để màn **"Khoán theo kỳ"** cắm nguồn mới vào, không phải dựng lại cột.

Màn "Khoán theo kỳ" (pha sau, ngoài bản này) sẽ đọc mẻ: việc khoán · sản lượng · danh sách người
tham gia · việc phát sinh kèm số lượng · ảnh chụp đơn giá lúc ghi mẻ; rồi **tự chia và tự nhân**
theo cách của kế toán. Bản này chỉ làm đủ dữ liệu cho màn đó — trước đây nó chỉ nhận được sản lượng
đã bị chia sẵn và tên đầu việc dự kiến.

## 10. Đổi dữ liệu

| Migration | Việc |
|---|---|
| `0313_cong_doan_vat_tu` | CREATE `cong_doan_vat_tu`; backfill gộp từ `cong_doan_dau_viec_vat_tu` theo `cong_doan_id` (trùng vật tư → giữ `thu_tu` nhỏ nhất) |
| `0314_piece_rates_cong_thuc_khoan` | ADD `piece_rates.cong_thuc_khoan`; backfill 1-1 từ `cong_doan_dau_viec.cong_thuc_khoan` |
| `0315_batch_viec_khoan` | ADD `san_xuat_batch.piece_rate_id` (nullable — mẻ cũ không có gì để backfill) + 3 ô ảnh chụp việc khoán (`ten_khoan_snapshot`, `don_vi_khoan_snapshot`, `don_gia_khoan_snapshot`); CREATE `san_xuat_batch_phat_sinh` (có `don_gia_snapshot`) |
| `0316_so_gio_ke_hoach` | ADD `so_gio_ke_hoach` cho `lsx_cong_doan` + `bai_ghep_cong_doan` (`Numeric(8,2)` NOT NULL default 0) |
| `0317_go_dau_viec_dinh_muc` | DROP `cong_doan_dau_viec_vat_tu`, `cong_doan_dau_viec` |
| `0318_go_kip_va_dau_viec_o_buoc` | DROP `khoan_json` (3 bảng), `so_nhan_cong_tieu_chuan` (2 bảng), `nang_suat` + `don_vi_nang_suat` (2 bảng), `san_xuat_phien_chay.ly_do_so_nguoi` |
| `0319_go_tang_chia_san_luong` | DROP 4 bảng phân bổ; DROP `san_xuat_ho_tro.ty_le_phan_tram` |

Thứ tự bắt buộc: backfill (`0313`–`0314`) **trước** khi drop (`0317`). Chạy lệch thứ tự là mất công
thức.

Backfill viết **raw SQL đích danh cột**, không ORM full-select — ORM sẽ kéo cột do migration sau
thêm và vỡ trên DB trung gian. Không cột Boolean nào nên không dính bẫy `server_default "0"/"1"`
(`so_gio_ke_hoach` là Numeric).

`docs/DB_SCHEMA.md` sửa **cùng lúc** — guard test bắt.

**Dữ liệu mất, không khôi phục:** năng suất khoán + kíp + cách đo giờ của 27 dòng định mức đầu việc;
ảnh chụp đầu việc trên bước lệnh và bước bài ghép; toàn bộ dòng chia sản lượng đã chốt + bù trừ +
loại trừ; tỷ lệ phần trăm của các phiếu hỗ trợ chéo. Chấp nhận được vì prod đang DB trắng và cột
lương khoán đã bằng 0 từ 11/09.

**Mẻ cũ sau bản này:** không có việc khoán, không có ảnh chụp giá, nên màn sản lượng hiện *"— chưa
khai việc khoán"* ở chỗ tên việc. Không tự gán, không đoán.

## 11. Thứ tự làm — LÀM MỘT LẦN

Đây là **một lần sửa**, không chia đợt. Chỉ có **đúng một ràng buộc thứ tự** và nó thuần kỹ thuật:

> `0313` + `0314` (chép vật tư và công thức sang chỗ mới) phải chạy **trước** `0317` (xoá chỗ cũ).
> Chạy lệch là mất công thức, không lấy lại được.

Còn lại làm cùng nhau, xác minh một lượt bằng luồng UI ở §13.

## 12. Không làm (bản này)

- **Màn "Khoán theo kỳ"** của kế toán lương — chỗ duy nhất chia và nhân ra tiền. Pha sau; đây là lý
  do cột khoán còn 0.
- **Bỏ khối "Phòng ban / Tổ phụ trách"** ở danh mục Công đoạn — chủ dự án đã bác rõ.
- **Đổi tên Xếp lịch 3 → Xếp lịch** và gỡ Xếp lịch 2 — session khác đang làm.
- **Nhiều việc khoán trong một mẻ** — *"chỉ chọn được một trong đó"*.
- **Công thức cho việc phát sinh** — nó nhân thẳng số lượng × đơn giá ở màn kế toán.
- **Dải min/TB/max cho thời lượng bước tổ** — một số nhập tay thì không có dải.
- **Gán việc phát sinh cho đích danh người** — mẻ chỉ ghi ở cấp mẻ.

## 13. Kiểm thử

**Backend** (pytest nhắm file, không chạy cả bộ):
`test_cong_doan.py` · `test_cong_doan_bon_cong_thuc_http.py` · `test_cong_doan_may.py` ·
`test_cong_viec_khoan.py` · `test_lsx_service.py` · `test_khsx_ui_contract.py` ·
`test_bai_ghep_service.py` · `test_san_xuat_san_luong.py` · `test_san_xuat_board.py` ·
`test_san_xuat_board_api.py` · `test_san_xuat_dong_nhom.py` · `test_danh_muc_tham_chieu.py` ·
`test_import_excel.py` · `test_khoan_api.py` · `test_db_schema_doc.py`
\+ bài mới cho từng migration `0313`–`0319`.

XOÁ: `test_khoan_dau_viec.py` · `test_san_xuat_phan_bo.py` · `test_migration_0270_gop_dinh_muc_nhan_luc.py` ·
`test_migration_0281_go_so_nguoi_bo_tri.py` · `test_migration_0272_0274_cong_thuc_ve_cong_doan.py` ·
`test_dong_bo_don_vi_khoan.py`.

**Frontend:** `npx tsc --noEmit` + XOÁ `DinhMucDauViec.test.tsx` · `ThsxChiaSanLuong.test.tsx`;
sửa `ThsxDrawer.test.tsx`; bài mới cho danh sách việc khoán ở form Ghi mẻ (phải KHÔNG có chữ "thành
tiền", KHÔNG có bảng chia).

**Luồng UI thật** (bắt buộc trước khi báo xong, không thay bằng curl một bước nào, kể cả để dựng
dữ liệu):

1. Danh mục Công đoạn → mở "Ghi kẽm CTP" → thấy khối "Đầu việc và định mức của tổ" đã mất, "Phòng
   ban / Tổ phụ trách" và hai khối Máy còn nguyên → tab Vật tư thêm 2 món kèm công thức → Lưu.
2. Danh mục Công việc khoán → mở "Bình bài & ra kẽm" → tab Công thức khoán gõ công thức → thêm 2
   việc phát sinh (tên + đơn giá + đơn vị) → Lưu. Gõ `binh bai` không dấu ở ô tìm, thấy đúng bản ghi.
3. **Cổng lập kế hoạch:** tạo lệnh có một bước tổ giao cho tổ CHƯA khai việc khoán nào → nút "Sẵn
   sàng lập kế hoạch" mờ, danh sách "Còn thiếu" hiện đúng câu *"Tổ … chưa khai công việc khoán"* →
   sang danh mục khai một việc cho tổ đó → quay lại, làm mới, mục thiếu biến mất, nút bấm được.
4. Mở drawer một bước tổ: **không còn** Kíp chuẩn và Đầu việc thợ làm, ô Tổ phụ trách vẫn chỉ mở ra
   tổ của công đoạn, ô Số giờ kế hoạch đang là 0 → gõ `4,5` (phải nhận số lẻ) → thử gõ chữ, phải
   không vào được → tab Vật tư thấy 2 món tự bung → Lưu công đoạn → Phát hành.
5. Bàn tổ đúng tổ đó → mở lệnh → mở bước → Ghi mẻ: ô tìm việc khoán **hiện sẵn** dù tổ chỉ vài việc
   → gõ không dấu tìm được → chọn "Bình bài & ra kẽm" (thấy đơn giá / ĐVT / ghi chú) → tick 2 việc
   phát sinh, nhập số lượng → điểm thêm **một thợ của tổ khác** vào mẻ → nhập sản lượng 1.000 → Lưu.
6. Mở lại mẻ: thấy việc khoán, 2 việc phát sinh kèm số lượng, **danh sách người tham gia** (người
   tổ khác có nhãn tổ gốc). **Không có bảng Chia sản lượng, không nút Tính/Chốt, không ô thành
   tiền, không số phút của ai.**
7. **Mẻ hai tổ:** mở tab Sản lượng của tổ chủ bước → mẻ 1.000 nằm ở mục "MẺ CỦA TỔ", có trong dòng
   tổng, danh sách người có nhãn tổ gốc cho người đi giúp → mở tab của tổ người đi giúp → **cùng
   mẻ, cùng 1.000**, nhưng nằm ở mục "người của tổ đi làm ở tổ khác", ghi rõ chủ mẻ là tổ nào, và
   **không** cộng vào dòng tổng của tổ đó. Không tab nào hiện 400/600.
8. **Băng "Danh mục đã đổi":** sang danh mục sửa đơn giá "Thay kẽm" 40.000 → 45.000 → quay lại mẻ →
   băng hiện đúng *"Thay kẽm · đơn giá 40.000 → 45.000"* → bấm "Giữ số cũ", mẻ vẫn 40.000 → bấm
   "Cập nhật theo danh mục", mẻ thành 45.000 và nhật ký có vết ai bấm.
9. Đăng nhập tài khoản thợ trong tổ đó → thấy "Các mẻ tôi tham gia": sản lượng cả mẻ + danh sách
   người tham gia, **không** có dòng "phần của tôi", **không** có số phút.
10. **Bảng lương:** mở kỳ tháng 9 → ô Khoán **vẫn còn đó** và vẫn bằng 0, y như trước khi sửa.
11. Danh mục Công việc khoán → thử xoá việc vừa ghi mẻ → phải bị chặn với câu nhắc đã có mẻ ghi.
