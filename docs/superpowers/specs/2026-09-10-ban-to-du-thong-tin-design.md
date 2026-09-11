# Bàn tổ đủ thông tin để làm — bước ngoài dòng giấy, dặn dò, kíp, quy cách, thời lượng — Thiết kế

**Ngày chốt:** 10/09/2026
**Phạm vi:** Danh mục Công đoạn · Kế hoạch SX (lệnh) · Phát hành SX (snapshot) · Thực hiện SX
(bàn tổ) — khối Kế hoạch + cột danh sách + ghi mẻ sản lượng.

---

## 1. Vấn đề

Mở bàn tổ của Tổ kỹ thuật, bước **Ghi kẽm CTP** của LSX26-0003 hiện:

- `SL vào → ra` = **0 → 0**, trong khi việc thật là **ghi 4 bản kẽm**;
- khối Sản lượng ghi *"0 tốt · mục tiêu 0 · đủ mục tiêu"* ngay lúc chưa ai chạm máy;
- không có câu dặn dò nào của người lập kế hoạch;
- không thấy kíp bao nhiêu người;
- không thấy quy cách in (giấy, khổ, số màu, số kẽm);
- chỉ thấy giờ hẹn, không thấy việc này ăn bao nhiêu phút và khoảng dao động ra sao.

Bốn nguyên nhân **khác nhau**, đã kiểm chứng trong code — đừng gộp làm một:

**(a) Bước ngoài dòng giấy bị hỏi bằng câu của tổ in.** Ghi kẽm không ăn tờ giấy nào nên nó đứng
ngoài chuỗi bù hao, `so_luong_vao/ra` để im ở 0 — có chủ ý ([lsx_service.py:2610](../../../backend/app/services/lsx_service.py)).
Engine đã có sẵn đường tính riêng cho nhóm bước này: `LsxService.buoc_ngoai_dong` chạy
`cong_doan.cong_thuc_san_luong` (vd `so_kem`) rồi suy ngược vế vào
([lsx_service.py:2050](../../../backend/app/services/lsx_service.py)). Nó im vì **danh mục chưa khai
công thức**: `seed_rebuild` khai CD-0001 với `cong_thuc_gia="so_kem * 95000"` nhưng bỏ trống
`cong_thuc_san_luong` ([seed_rebuild.py:358](../../../backend/app/seed_rebuild.py)) — trong khi
danh mục prod thì khai đủ ([import_danh_muc_prod.py:323](../../../backend/app/import_danh_muc_prod.py)).
Và **ô khai đó đã bị ẩn khỏi drawer Công đoạn từ 07/09/2026**
([rebuildCatalogConfigs.tsx:437](../../../frontend/src/pages/rebuildCatalogConfigs.tsx)), nên người
khai danh mục không còn cửa nào sửa. Cột + engine vẫn nguyên vẹn.

**(b) Dặn dò rơi mất trên đường xuống xưởng.** Kế hoạch có ô *"Ghi chú kỹ thuật cho thợ"*
(`lsx_cong_doan.ghi_chu`, [LsxBuocDrawer.tsx:594](../../../frontend/src/pages/LsxBuocDrawer.tsx)),
nhưng `snapshot._cong_viec_theo_phan_doan` không chụp trường này
([snapshot.py:258](../../../backend/app/services/san_xuat/snapshot.py)).

**(c) Kíp người đã xuống tới nơi nhưng không cho ai xem.** `du_kien_so_nguoi` có trong payload work
item ([board.py:228](../../../backend/app/services/san_xuat/board.py)); FE chỉ dùng nó ngầm để bắt
lý do khi roster lệch lúc Bắt đầu ([ThucHienSxPage.tsx:558](../../../frontend/src/pages/ThucHienSxPage.tsx)).
Tổ trưởng bị chặn bởi một con số mình không được nhìn.

**(d) Quy cách và dải thời lượng chưa từng được chụp.** `snapshot` có dựng `quy_cach_bien(lsx)`
cho việc tính đơn giá rồi bỏ đi ([snapshot.py:66](../../../backend/app/services/san_xuat/snapshot.py));
`_dinh_muc` chỉ chụp `chay_phut`, bỏ `chay_phut_min/max` mà `thoi_luong_buoc` đã tính sẵn từ dải
tốc độ máy ([lsx_service.py:412](../../../backend/app/services/lsx_service.py)).

## 2. Nguyên tắc

> Thẻ việc thả xuống tổ phải **tự đủ để làm**: đo bằng đơn vị của chính công việc đó, mang theo
> dặn dò, kíp, quy cách và khoảng thời gian. Tổ không phải hỏi miệng, không phải tra ngược hồ sơ
> lệnh — mà cũng **không được phép** tra: tổ trưởng không có quyền `lsx`.

Ba hệ quả bắt buộc:

- Thông tin đi xuống bằng **ảnh chụp lúc phát hành**, không đọc sống lên lệnh (giữ đúng §4.2 của
  module: lệnh còn sửa được sau khi phát hành).
- Màn hạ nguồn **chỉ đọc và hiện**, không tự suy diễn lại — cờ "ngoài dòng giấy" phải được chụp,
  không để FE đoán từ mã đơn vị.
- Việc gì danh mục đã trả lời được thì **khai ở danh mục**, không đẻ ô nhập mới trên từng lệnh.

## 3. Bước ngoài dòng giấy đo bằng đơn vị của chính nó

### 3.1 Danh mục Công đoạn — trả lại cửa khai

- **Hiện lại** ô *"Công thức sản lượng ra"*, chỉ khi hai ô đơn vị chặng đều trống (= bước ngoài
  dòng giấy). Ô này bị ẩn ngày 07/09/2026; bỏ chốt ẩn là đủ, backend không đụng.
- **Thêm** ô *"Đơn vị sản lượng"* ngay dưới nó, chọn từ danh mục Đơn vị & quy đổi (vd `kem` —
  *bản kẽm*). Cột mới `cong_doan.don_vi_san_luong VARCHAR(24)`, ánh xạ `don_vi_do.ma`.
  Chỉ có nghĩa với bước ngoài dòng giấy; bước trên dòng đã có đơn vị chặng.

  *Vì sao không mượn đơn vị sẵn có:* `may_thiet_bi.don_vi_toc_do` là đơn vị **đo giờ**,
  `khoan_json.don_vi` là đơn vị **tính tiền** — hai thứ cố ý tách rời, và bước tổ ngoài dòng thì
  không có máy nào để mượn.

- Khai cho dữ liệu hiện có: CD-0001 *Ghi kẽm CTP* → công thức `so_kem`, đơn vị `kem`. Sửa cả
  `seed_rebuild.py` (dev) lẫn `import_danh_muc_prod.py` (thêm `don_vi_san_luong` cho CD-1001,
  CD-1003 vốn đã có công thức).

### 3.2 Kế hoạch — số tự hiện, không ai gõ tay

Khai xong (3.1) thì `buoc_ngoai_dong` tự cho **SL ra = 4 bản kẽm**; vế vào suy ngược qua hệ số 1,0
và bù hao của công đoạn (CD-0001 để `khong`) ⇒ **vào = ra = 4**. Không sửa engine.

Sửa một chỗ nhỏ: `_san_luong_dien_giai` đang tra tên đơn vị theo `don_vi_ra` (trống với bước ngoài
dòng) nên câu diễn giải hiện *"Số bản kẽm = 4"* cụt đuôi — cho nó đọc `don_vi_san_luong` để ra
*"Số bản kẽm = 4 bản kẽm"*.

### 3.3 Phát hành — đơn vị đi theo công việc

Snapshot ghi `san_xuat_cong_viec.don_vi_vao` / `don_vi_ra` = `cong_doan.don_vi_san_luong` khi bước
ngoài dòng giấy (hiện đang chép `cd.don_vi_vao/ra` — trống).

Đây là điểm rẻ nhất của cả thiết kế: trong module Thực hiện SX, hai cột ấy chỉ đóng vai **đơn vị
bản địa của bước** — ghi mẻ sản lượng ([san_luong.py:207](../../../backend/app/services/san_xuat/san_luong.py)),
bàn giao, KCS, yêu cầu kho, phân bổ lương đều đọc chúng. Điền đúng một chỗ thì cả năm khối hạ
nguồn tự có đơn vị, **không cột mới, không sửa từng khối**.

Luật `tren_dong_giay` không bị ảnh hưởng: nó chấm "hai đầu đều là chặng", mà `kem` không phải
chặng — và trong module SX luật đó chỉ chạy trên bản ghi kế hoạch (`cd`), không chạy trên công
việc (`cv`).

Chụp thêm vào `dinh_muc_json` (JSON sẵn có, không cần cột):

| Khoá | Nội dung |
|---|---|
| `ngoai_dong` | `true` với bước ngoài dòng giấy — FE không phải đoán lại từ mã đơn vị |
| `sl_dien_giai` | câu *"Số bản kẽm = 4 bản kẽm"* của 3.2 |

### 3.4 Bàn tổ — hiện một số, kèm câu vì sao

- Cột danh sách: bước ngoài dòng đổi `0 → 0` thành **`4 bản kẽm`** (một số, vì vào = ra; hiện hai
  lần chỉ là nhiễu). Tiêu đề cột giữ nguyên *"SL vào → ra"* cho bước trên dòng giấy.
- Khối Kế hoạch của drawer: thay hai dòng *SL vào* / *SL ra* bằng một dòng **Khối lượng** kèm câu
  `sl_dien_giai` in nhỏ bên dưới.
- Khối Sản lượng: `muc_tieu` nay là 4 (đọc `so_luong_ra` như cũ, số đã đúng) ⇒ hết cảnh *"mục tiêu
  0 · đủ mục tiêu"*; ô Ghi mẻ hiện *"Số lượng (bản kẽm)"*.

## 4. Dặn dò của kế hoạch đi theo bước

Cột mới `san_xuat_cong_viec.ghi_chu TEXT`, chụp từ `lsx_cong_doan.ghi_chu` lúc phát hành (bài ghép
cũng có trường tương ứng). Bàn tổ hiện thành một khối **Dặn dò của kế hoạch** ngay dưới khối Kế
hoạch, chỉ hiện khi có chữ.

`yeu_cau_ky_thuat` (yêu cầu gửi nhà gia công) **không** chụp: nó viết cho nhà thầu, không phải cho
tổ trong xưởng.

## 5. Kíp người — chỉ là hiển thị

Không đụng backend. Khối Kế hoạch thêm dòng **Kíp chuẩn `N` người · đang có `M`**, đọc
`du_kien_so_nguoi` (đã có sẵn trong payload) và roster `active`. Lệch thì tô cảnh báo và nói trước
rằng bấm Bắt đầu sẽ phải chọn lý do — thay vì để hộp lý do nhảy ra bất ngờ.

## 6. Quy cách in rút gọn

Cột mới `san_xuat_cong_viec.quy_cach_json JSON` (dùng `none_as_null=True`, cùng lý do với
`kcs_tieu_chi_json`). Chụp lúc phát hành từ `quy_cach_bien(lsx)` / `quy_cach_bien_bai(bai)` —
snapshot đã dựng sẵn hai dict này cho việc khác, chỉ là chưa lưu.

Chụp **chọn lọc**, đủ để đứng máy, không bê cả `quy_cach_json` của lệnh:

| Khoá | Ý nghĩa | Nguồn |
|---|---|---|
| `giay` · `dinh_luong` | tên giấy + gsm | `quy_cach_json` của lệnh |
| `kho_in` | khổ tờ in (dài × rộng, mm) | `dai_in` · `rong_in` |
| `kho_tp` | khổ thành phẩm | `dai_tp` · `rong_tp` |
| `so_mat` · `so_mau` | mấy mặt · mấy màu | `ngu_canh_lenh` |
| `so_kem` | số bản kẽm | `ngu_canh_lenh` |
| `so_con` | con/tờ | cột `lsx.so_con` |
| `so_luong` | SL đặt của đơn | cột `lsx.so_luong_dat` |
| `ghi_chu_ky_thuat` | ghi chú kỹ thuật theo sản phẩm, chốt từ khâu tính giá | `lsx_service` |

Bàn tổ hiện thành khối **Quy cách** gấp/mở, mặc định gấp. Cùng một thẻ cho mọi tổ — không lọc theo
tổ ở bản này (xem §9).

## 7. Dải thời lượng

`_dinh_muc` chụp thêm `chay_phut_min` / `chay_phut_max`. Hai số này **không có cột sẵn** như
`chay_phut` — snapshot phải gọi `thoi_luong_buoc(cd, may, sl_tinh)`, thứ đã tính chúng từ
`may_thiet_bi.toc_do_min/max` ([lsx_service.py:412](../../../backend/app/services/lsx_service.py)).
Máy chưa khai dải thì ba số bằng nhau. Dựng service **trễ + cache theo lệnh**, đúng khuôn
`_DonGiaHieuDung` đã có trong chính file snapshot — gói không có bước máy nào thì không đụng tới
`LsxService` lần nào.

Bàn tổ hiện ở khối Kế hoạch: **Chạy máy 13 phút (11 – 15)**. Ba số bằng nhau thì bỏ phần ngoặc.

**Không** đưa xuống tổ hai mốc *"sớm nhất / muộn nhất"* của panel Xếp lịch: đó là biên **lịch**,
đổi mỗi lần xếp lại, và thợ đọc nó sẽ hiểu thành "được phép làm trễ tới 14:22".

## 8. Thay đổi dữ liệu

Ba cột mới, hai migration — số thứ tự lấy kế tiếp cuối `db_migrations.py` lúc thi công (không cột
Boolean nên không dính bẫy `server_default "0"/"1"`):

| Migration | Bảng | Cột |
|---|---|---|
| `…_cong_doan_don_vi_san_luong` | `cong_doan` | `don_vi_san_luong VARCHAR(24) NULL` |
| `…_san_xuat_cong_viec_ghi_chu_quy_cach` | `san_xuat_cong_viec` | `ghi_chu TEXT NULL` · `quy_cach_json JSON NULL` |

`docs/DB_SCHEMA.md` cập nhật **cùng lúc** (guard test bắt).

**Lệnh đã phát hành không được backfill.** Số lượng của bước ngoài dòng phải do kế hoạch tính lại
mới đúng, mà đó là việc của người lập kế hoạch chứ không phải của migration. Lệnh cũ như 0003 lấy
đủ thông tin bằng **Phát hành cập nhật**; migration chỉ thêm cột rỗng.

## 9. Không làm (bản này)

- **Lọc quy cách theo tổ** (chế bản thấy kẽm/màu, in thấy giấy, sau in thấy khổ + dao). Thẻ rút
  gọn ở §6 chỉ 8 dòng — lọc thêm là dựng bảng ánh xạ tổ × trường để tiết kiệm 3 dòng chữ.
- **Biên lịch sớm nhất / muộn nhất** xuống tổ — xem §7.
- **Phiếu công nghệ PDF** nhận cùng bộ dữ liệu. Đúng hướng, nhưng là đầu ra khác, làm sau khi bàn
  tổ chạy ổn.
- **Ô nhập số lượng tay cho bước ngoài dòng** trên lệnh. Công thức danh mục trả lời được thì đừng
  mở đường gõ đè — hai nguồn số là hai số lệch nhau.

## 10. Kiểm thử

Backend (pytest, nhắm file):

- `buoc_ngoai_dong` với công đoạn khai `so_kem` + đơn vị `kem` → vào = ra = 4, câu diễn giải có
  đuôi *"bản kẽm"*.
- Snapshot một lệnh có bước ngoài dòng → công việc mang `don_vi_vao/ra = "kem"`,
  `dinh_muc_json.ngoai_dong = true`, `ghi_chu` đúng chữ của kế hoạch, `quy_cach_json` đủ 8 khoá,
  `chay_phut_min/max` có mặt.
- Ghi mẻ sản lượng trên bước ấy: đơn vị mặc định ra `kem`, `muc_tieu = 4`, `con_thieu` giảm dần.
- Bước trên dòng giấy: mọi số giữ nguyên như trước (test hồi quy).

UI — thao tác thật trên dev-browser, đúng luồng, không dùng API tắt bước nào:

1. Danh mục Công đoạn → mở CD-0001 → khai công thức `so_kem` + đơn vị `kem` → Lưu.
2. Kế hoạch SX → lệnh có bước Ghi kẽm → bước hiện `4 → 4 bản kẽm` + câu diễn giải.
3. Drawer bước → gõ ghi chú kỹ thuật cho thợ → Lưu công đoạn.
4. Phát hành cập nhật.
5. Bàn tổ · Tổ kỹ thuật → thẻ việc hiện `4 bản kẽm`, khối Dặn dò có đúng câu vừa gõ, Kíp chuẩn
   hiện số, khối Quy cách xổ ra đủ giấy/khổ/màu/kẽm, dòng Chạy máy có dải phút.
6. Ghi mẻ 2 bản → *"còn thiếu 2 bản kẽm"*; ghi nốt 2 → *"đủ"*.

## 11. Thứ tự thi công

1. Migration + `DB_SCHEMA.md` (§8).
2. Danh mục Công đoạn: cột `don_vi_san_luong`, mở lại ô công thức, seed/import (§3.1).
3. Kế hoạch: câu diễn giải đọc đơn vị mới (§3.2).
4. Snapshot: đơn vị + `ngoai_dong` + `sl_dien_giai` + `ghi_chu` + `quy_cach_json` +
   `chay_phut_min/max` (§3.3, §4, §6, §7).
5. `board._item_dict` + schema `san_xuat.py` trả các trường mới.
6. Bàn tổ: cột danh sách, khối Kế hoạch, Dặn dò, Kíp, Quy cách, ô Ghi mẻ (§3.4, §4, §5, §6, §7).

Bước 1–3 đã đủ để bước ngoài dòng hết cảnh `0 → 0` trên màn Kế hoạch; 4–6 là phần đưa nó xuống tổ.
