# Bài ghép — sổ lỗi còn nợ (lát "người dùng tự gộp công đoạn")

Ghi ngày **2026-08-03**, trên cây làm việc CHƯA COMMIT, base `11a0152`, nhánh `dev`.

Nguồn: tự soi trong lúc thi công + một lượt review độc lập bằng agent (agent được dặn KHÔNG tin
mục "Trạng thái thi công" trong plan, phải tự đọc code và chạy probe thật).

**Cột "kiểm"**: `tôi` = tôi đã tự mở file xác nhận · `probe` = agent chạy script dựng fixture thật
rồi in số · `đọc` = agent kết luận bằng đọc code, tôi chưa kiểm lại.

> Số dòng ghi ở đây là **tại thời điểm review**. Các mục ở §0 đã sửa sau đó nên
> `bai_ghep_service.py`, `xep_lich_service.py`, `test_bai_ghep_service.py` đã xê dịch nhiều dòng.

**Tổng: 35 đã sửa · 6 còn nợ** (0 nặng · 0 lệch plan · 0 trung bình · 0 lỗ test · 6 vặt).

> Bản trước ghi "19 còn nợ (9 trung bình)" nhưng §3 đếm tay ra **10 dòng** — thêm `M12` và dòng
> `MỚI` mà quên bump số. Con số ở đây đã đếm lại.

**Cập nhật 2026-08-03:**
- **Đợt 2** — đã sửa **hết 5 lỗi nặng** S2–S6, mỗi cái kèm test khoá, vì cả năm đều lọt qua bộ
  1125 test cũ.
- **Đợt 3** — quy đổi đơn vị vào→ra của bước chung nay **dùng chung engine với tính giá**
  (`chuoi_nguoc_dv` + bảng cầu), bỏ vòng lặp tự cuộn và `if` cứng một cặp đơn vị. Chạy ví dụ số
  thật thì lòi thêm lỗi thẻ bước bị đè — đã sửa luôn.

- **Đợt 4** — làm **hết 8 mục lệch plan** (§2), kèm M1 + M10. Còn nợ **`khoan_json` chưa có UI**.
- **Đợt 5** — case sách ở tầng LỆNH SX: `_he_so_cau` thiếu nhánh `1/so_tay` (xem §0).
- **Đợt 6** — **ruột sách bị CHẶN khỏi bài ghép**. Một cuốn 10 tay = 10 tờ in khác nhau, mô hình
  bài ghép giả định mỗi thành viên góp MỘT bố cục tờ nên không diễn tả nổi. Chặn ở **cả hai cửa**:
  `hang_cho_ghep()` (lọc hiển thị) và `_validate_them()` (cửa ghi — API gọi thẳng được). Tiêu chí
  dùng chung `thanh_phan_engine.la_gap_tay()`, cùng hàm `cau_to_sang_cai` dùng để chọn nhánh hệ số.
  **Bìa sách vẫn ghép bình thường.** Test: `test_ruot_sach_khong_vao_duoc_bai_ghep` (có cả ca
  ngược — bìa không bị chặn nhầm).

- **Đợt 7 (2026-08-04)** — làm **hết §3 (10 mục trung bình)**. Kèm 1 migration (`0152`) và 5 test
  khoá. Chi tiết ở chính §3.
- **Đợt 8 (2026-08-04)** — lấp **hết §4 (4 lỗ test)**. Mở hẳn bộ chạy test FE (**vitest + jsdom**,
  repo trước nay chưa có) và nối vào cổng kiểm CI. Mọi test mới đều được **hạ code về bản cũ để
  xem nó có đỏ không** trước khi tính là xong — bài học từ cái test giả ở §0.

Chi tiết ở §0, §2, §3 và §4. **6 mục còn nợ nằm ở §5.**

---

## §0. ĐÃ SỬA (11)

### Đợt 2 — cụm 5 lỗi NẶNG (2026-08-03)

| # | Lỗi | Đã sửa thế nào | Test khoá |
|---|---|---|---|
| **S2** | `LsxBaiGhepOut` thiếu `buoc_bi_de` → pydantic lọc mất field → badge mã bài ghép và hai-số ở màn lệnh là **code chết** (FE optional-chaining nên không crash, chỉ im lặng) | `schemas/lsx.py`: thêm model `BuocBiDeOut` + trường `buoc_bi_de: dict[str, BuocBiDeOut]`, bỏ `buoc_in_step_key` | `test_khoi_bai_ghep_cua_lenh_khong_bi_response_model_nuot` — assert **mọi khoá service trả sống sót qua response model** (`set(d) <= set(ra)`), không chỉ riêng field này |
| **S3** | Cột `so_luong_vao/ra/hao_hut` của `bai_ghep_cong_doan` không ai ghi, luôn 0 — mà `thoi_luong_buoc()` đọc `so_luong_vao` để suy giờ chạy, và `lsx_service` đọc để dựng `buoc_bi_de` | Tách `_chuoi_chung()` làm **một nguồn duy nhất** cho chuỗi chung, thêm cửa ghi `_ap_so_luong_chung()` (đúng kiểu `_ap_chuoi_nguoc` của lệnh) + `_tinh_lai()` gọi cả hai tầng đúng thứ tự. Nối vào **mọi cửa làm số đổi**: gộp · tách · thêm/bỏ thành viên · sửa con/tờ · sửa khổ & hao · lập kế hoạch bước chung | `test_so_luong_buoc_chung_duoc_GHI_xuong_db` — cột > 0, và đổi `con/tờ` thì số phải đổi theo (chống ghi một lần rồi thiu) |
| **S4** | Bài chỉ đẻ **một** dòng `in_ghep` trong khi `_sinh_dong` loại **mọi** bước bị đè → gộp CTP+In+Cán là 2 bước bốc hơi khỏi board; dòng đó lại dùng `bg.may_id`, vứt máy/thời lượng vừa khai ở drawer | Cột mới `xep_lich_cong_doan.bai_ghep_cong_doan_id` + migration **`0151`** + DB_SCHEMA. `dua_vao_bai_ghep` sinh **mỗi bước chung một dòng**, lấy máy/tổ/NCC từ chính bước chung. `_thoi_luong` dùng `_thoi_luong_noi_bo` cho dòng có neo (duck-type: `BaiGhepCongDoan` mirror `LsxCongDoan`). Board hiện **tên thật** của bước thay vì "In chung". Dòng cũ (`NULL`) giữ nhánh cũ nên bài đã lập KH không vỡ | `test_moi_buoc_chung_mot_dong_lich_khong_bi_boc_hoi` — gộp 2 công đoạn phải ra **2 dòng**, dòng phải có neo, máy = máy bước chung (bài `may_id=None`), `chay_phut` = số gõ đè, và lệnh không còn dòng riêng |
| **S5** | `bo_thanh_vien` để lại `bai_ghep_cong_doan_map` mồ côi → lệnh đã rời bài vẫn bị chặn sửa routing mà UI không còn đường tách, lại vẫn bị bỏ hao (mua thiếu giấy) | Thêm `_go_lop_de(bg, lsx_id)`: xoá map của lệnh rời, và **xoá luôn bước chung còn dưới 2 lệnh** (một lượt "chung" một mình thì không còn là chung), rồi sắp lại `thu_tu` | `test_lenh_roi_bai_thi_lop_de_di_theo` — map về 0, bước chung biến mất, và lệnh vừa rời **sửa routing được ngay** |
| **S6** | Thiếu nhãn `thieu_buoc_chung` / `thieu_ke_hoach_buoc_chung`, thừa `thieu_buoc_in` → mọi bài mới tạo hiện chữ mã trần | `client.ts`: thay bằng hai nhãn tiếng Việt có hướng dẫn hành động | — (nhãn hiển thị) |

### Đợt 3 — quy đổi đơn vị làm giống engine tính giá (2026-08-03)

Anh chỉ ra: *"chỗ quy đổi của các đơn vị vào → ra ở từng công đoạn thì làm giống tính giá ấy"*.
Tôi đang tự cuộn vòng lặp riêng cho chuỗi chung, và `if` cứng đúng một cặp `to → cai`.

| Sửa | Trước | Sau |
|---|---|---|
| Bộ đi chuỗi | `_chuoi_chung` tự cuộn vòng `for c in reversed(chungs)` | Gọi thẳng **`bu_hao_engine.chuoi_nguoc_dv`** — đúng hàm engine tính giá đang chạy (`thanh_phan_engine` dùng nó) |
| Hệ số quy đổi | `if (don_vi_vao, don_vi_ra) == (DV_TO, DV_CAI)` — cặp nào chưa nghĩ tới thì âm thầm chạy hệ số 1 | **Bảng cầu** `_cau_quy_doi()` cùng hình dạng `he_so_dv` bên tính giá. Cặp thiếu hệ số → hàm chung **kêu warning**, không lặng lẽ lấy 1 |
| Giá trị cầu `to → cai` | `Σ số con` của các thành viên | `Σ` **`cai_moi_to`** từng thành viên, chép đúng luật `thanh_phan_engine:384`: **cắt rời** góp `con_i`, **gấp tay** góp **`1/so_tay_i`** (nhỏ hơn 1, và `con` KHÔNG vào công thức giấy). Lấy `con` cho sách là 10 tờ ra 1 cuốn mà tính thành 1 tờ ra N cuốn — lệch cả chục lần số giấy |
| Nguồn `so_tay` | — | **Tính lại** từ `so_trang / trang_moi_tay`, KHÔNG đọc `so_to_per_sp` đã lưu. Bản đầu tôi ưu tiên snapshot đó và ăn ngay bug: fixture có `so_to_per_sp = 1` cũ nên sách ra hệ số 1 thay vì 0,1. `so_to_per_sp` là thứ engine **ghi ra**, không phải thứ nó đọc vào |
| `ra_quy` + `he_so` | Không trả ra | Trả trên thẻ chung (`so_luong_ra_quy`, `he_so_quy_doi`) đúng như `bu_hao_chi_tiet`. Tính giá cố ý trả hai số này kèm comment *"không có thì dòng đổi đơn vị đọc lên vô lý"* — thẻ bài ghép trước đó dính đúng lỗi ấy |
| Làm tròn | Hiệu số thô | `ceil(vào) − ceil(ra/hệ_số)` — y hệt `bu_hao_chi_tiet`, để hai màn không lệch nhau 1 đơn vị |
| Bậc bù hao | Tra bằng `so_to_tot` (số TỜ) cho **mọi** bước | Tra theo `ra` của **chính bước đó, đúng đơn vị của nó** — bước bế đếm CON thì bậc là số con. Đây đúng là thứ `chuoi_nguoc_dv` sinh ra để chữa |
| Chuỗi đứt đơn vị | Không ai kiểm | Hàm chung kêu *"bước X ra `cai` nhưng bước Y vào `to` — chuỗi đứt đơn vị"*, trả lên `so_do` qua khoá `canh_bao_don_vi` |
| `hao_hut` | `vao - ra` tự tính | `hao` của hàm chung = `vào − ra_quy`, tức đếm ở **đơn vị VÀO** — thứ mất trên máy là tờ, không phải con |

**Lỗi lòi ra khi chạy ví dụ số thật** (làm xong mới thấy — đúng lý do phải chạy ví dụ):
thẻ bước **BỊ ĐÈ** bên nhánh đang hiện **nhu cầu riêng** của lệnh chứ không phải số nó thật sự
nhận từ lượt chung. Lệnh nhỏ cần 4.000 tờ, bài chạy 5.075 tờ → thẻ ghi "4.000 tờ → 8.000 cái"
trong khi ngay cạnh là chip *"dư tờ 1.075"* và nhánh ghi *"sản lượng 10.150"*. Ba con số trên cùng
một màn đá nhau. Đã sửa: bước bị đè lấy số của lượt chung, qua cầu thì nhân `cai_moi_to` của
**chính lệnh đó** (5.075 → 10.150). Test: `test_the_buoc_bi_de_hien_so_cua_luot_chung_khong_phai_nhu_cau_rieng`.

Test khoá:
- `test_quy_doi_don_vi_buoc_chung_tra_BANG_CAU_giong_tinh_gia` — bài toàn cắt rời: hệ số = 4 + 2
  = 6 (**tổng**, không phải con của một lệnh), vào đếm tờ / ra đếm con.
- `test_cau_to_sang_cai_theo_cai_moi_to_khong_phai_so_con` — trộn một lệnh **sách** (160 trang,
  16 trang/tay → 10 tờ = 1 cuốn): lệnh sách góp **0,1**, lệnh cắt rời góp **2** → cầu = 2,1.
  Nếu quay lại `Σ con` thì ra 6, test đỏ ngay.

> **✅ ĐÃ SỬA (đợt 5, 2026-08-03) — case sách ở tầng LỆNH SẢN XUẤT.**
> `lsx_service._he_so_cau` từng trả thẳng `con` cho cầu `to → cai`, **thiếu nhánh `1/so_tay`** →
> lệnh sách cấp thiếu giấy đúng `con × so_tay` lần, một chiều. Migration `0148` đã dựng sẵn cầu
> `to → cai` cho "Bắt tay + vào keo" (CD-0008); chỉ thiếu đúng hệ số đi qua cầu.
>
> Sửa bằng cách đưa luật về **một nguồn duy nhất**: `thanh_phan_engine.cau_to_sang_cai()`. Cả ba
> tầng nay gọi cùng hàm — tính giá (`compute_phieu`), lệnh (`_he_so_cau`), bài ghép
> (`_cai_moi_to`, bỏ bản chép). Test khoá: `test_cau_to_sang_cai_sach_gap_tay_nguoc_chieu_voi_cat_roi`
> (sách 160 trang tay 16 → hệ số 0,1 dù `so_con` = 8; hàng cắt rời vẫn = `con`) và
> `test_chuoi_nguoc_sach_can_nhieu_to_hon_so_cuon` (2.000 cuốn → **20.000 tờ**, không phải 250).
> Cả hai đều ĐỎ trên code cũ.
>
> **Dữ liệu cũ:** `so_to_ke_hoach` / `so_to_nguyen` là cột LƯU, chỉ ghi lại khi `_ap_chuoi_nguoc`
> chạy (tạo · sửa routing · đổi con/tờ · vào–ra bài ghép). Lệnh sách tạo trước hôm nay giữ số cũ
> tới khi bị chạm. Đếm trên DB dev phiên này: **9 lệnh, 0 lệnh sách** → không có gì phải backfill.
> DB prod chưa kiểm.

### Đợt 1 — trong lúc thi công / ngay sau review

| # | Lỗi | Ai tìm |
|---|---|---|
| S1 | `to_nguyen_can` chia nhầm cầu: lấy hệ số của **bước toả** (bế = con/tờ) thay vì cầu `to_nguyen → to` (số mảnh xả). 5.075 tờ với 4 con/tờ ra **1.269** tờ nguyên — hiện thẳng trên header với nhãn "Giấy lĩnh kho", ai cầm đi lĩnh giấy là thiếu 3/4. Đã sửa + có test khoá (`test_to_nguyen_can_di_qua_cau_to_nguyen_sang_to`) | agent |
| M11 | Thẻ bước chung đóng đinh `don_vi_vao = don_vi_ra = to`. Bước gộp là `to → cai` thì thẻ ghi "5.075 tờ ➔ 5.075 tờ" trong khi thẻ liền kề ghi "vào 20.300 cái". Đã sửa: `gop()` snapshot đơn vị từ bước gốc; `to → cai` thì RA nhân **tổng con của mọi lệnh trên tờ** | agent (anh chỉ ra nguyên nhân: đơn vị vào/ra là thứ NGƯỜI khai ở danh mục công đoạn) |
| — | Test giả: `assert chung["so_luong_vao"] - chung["so_luong_ra"] == chung["hao_hut"]` là **hằng đẳng thức** (`_node_chungs` viết thẳng `hao_hut = vao - ra`), không bao giờ đỏ được. Tên test hứa "hao đếm đúng một lần" nhưng không assert trị số nào. Đã thay bằng: tra bù hao ở bậc số tờ của bài rồi so bằng `pytest.approx`, cộng assert `hao_setup_de_xuat` = 1 bộ | agent |
| — | `_hs_tai_buoc` thành code chết sau khi sửa S1 → đã gỡ | tôi |

---

## §1. NẶNG — ĐÃ SỬA HẾT (5/5)

> Giữ lại nguyên văn chẩn đoán để sau này còn tra. Cách sửa + test khoá xem §0.

### S2 ✅ ĐÃ SỬA — `LsxBaiGhepOut` thiếu `buoc_bi_de` → toàn bộ tính năng "phía lệnh" là code chết
- **Chỗ**: `backend/app/schemas/lsx.py:371-381` vẫn khai `buoc_in_step_key`, không có `buoc_bi_de`.
- Service trả dict có `buoc_bi_de` nhưng FastAPI validate qua model này nên **field bị bỏ**.
- **Hậu quả** (FE dùng optional chaining nên không crash — nó *im lặng không làm gì*):
  - `frontend/src/components/DagRoutingCanvas.tsx:835` → `maBaiGhep` luôn `null` → **badge mã bài
    ghép không bao giờ hiện** trên routing của lệnh.
  - `frontend/src/pages/LsxBuocDrawer.tsx:120-121` → `deLen` luôn `null` → **ô máy KHÔNG bị khoá**,
    không hint hai số, không link mở bài. Đoạn code hai-số ở `LsxBuocDrawer.tsx:624-638` chết hẳn.
- **Kiểm**: tôi. Đây là bước 10 của plan → coi như chưa làm.

### S3 ✅ ĐÃ SỬA — Cột `so_luong_vao` / `so_luong_ra` / `hao_hut` của `bai_ghep_cong_doan` luôn = 0
- `gop()` không set (`bai_ghep_service.py:470-482`); `_SUA_DUOC_BUOC_CHUNG` cố tình loại
  (`:526-532`); `_node_chungs` tính lúc đọc rồi **không ghi lại** (`:894-903`).
- Nhưng `lsx_service.py:1352-1357` **đọc chính mấy cột đó** để dựng `buoc_bi_de`.
- **Hậu quả**: sửa xong S2 thì drawer lệnh vẫn in *"bài cấp 0 tờ"*. Hai lỗi chồng nhau trên cùng
  một tính năng.
- **Kiểm**: probe (gộp 3 bước → cả 3 đều `vao=0.00 ra=0.00 hao=0.00`).
- **Đã chốt**: **GHI vào cột**, không bỏ cột. Lý do: `thoi_luong_buoc()` đọc thẳng `so_luong_vao`
  để suy giờ chạy, và `lsx_cong_doan` cũng lưu số dẫn xuất y hệt (`_ap_chuoi_nguoc` là cửa ghi).
  Nguyên tắc của repo không phải "không lưu" mà là "**một cửa ghi duy nhất**" — nay là
  `_ap_so_luong_chung`.

### S4 ✅ ĐÃ SỬA — Gộp bước ngoài bước in → bước đó BIẾN MẤT khỏi bàn xếp lịch
- `xep_lich_service.py:483` sinh **đúng một** dòng `NGUON_IN_GHEP` dùng `bg.may_id`, trong khi
  `_sinh_dong` (`:433-447`) nay loại **mọi** bước bị đè.
- **Hậu quả**:
  - Gộp CTP + In + Cán → 3 bước biến mất khỏi board: không đặt chỗ máy, không vào chuỗi `_chuoi`,
    không tính thời lượng.
  - Dòng duy nhất đó dùng `bg.may_id` + `_thoi_luong_in_ghep` (`:277-286`) nên **vứt bỏ toàn bộ
    máy / `chay_phut` / `setup_phut` người dùng vừa khai trong drawer bước chung**.
  - Bài chỉ gộp Cán màng (không gộp In) vẫn đẻ một dòng "in ghép", trong khi mỗi lệnh vẫn giữ
    dòng In riêng → **đặt chỗ máy in trùng**.
- **Kiểm**: tôi (đọc code) + probe (`dòng của bài: [('in_ghep', 0, None)]`, `LSX 1: []`, `LSX 2: []`).
- Bước 11 của plan ("sẵn sàng xếp lịch") coi như vỡ.

### S5 ✅ ĐÃ SỬA — `bo_thanh_vien` để lại map MỒ CÔI → khoá routing lệnh vĩnh viễn
- `bai_ghep_service.py:268-285` gỡ `BaiGhepThanhVien` nhưng không đụng `bai_ghep_cong_doan_map`
  (map neo `lsx_id`, không có FK tới thành viên).
- **Hậu quả**:
  - Lệnh đã rời bài vẫn bị chặn sửa routing: *"Bước … đang chạy chung trong bài ghép GB26-0001 —
    tách bước khỏi bài trước"*. Người dùng vào ngõ cụt: lệnh không còn trong bài nên UI **không có
    đường nào** để tách.
  - `_buoc_ghep_keys(lsx_id)` và `_bo_hao_do_ghep(lsx)` vẫn đọc map mồ côi → lệnh đó **bị bỏ hao**
    ở bước in dù không còn ghép với ai → số giấy phải mua bị hụt.
  - Thẻ chung hiện chip mã rỗng (`(1, None)`), và thêm lại thành viên thì lớp đè cũ **sống dậy im
    lặng**.
- **Kiểm**: probe.

### S6 ✅ ĐÃ SỬA — Checklist "còn thiếu" hiện mã máy thay vì tiếng Việt
- `frontend/src/api/client.ts:312-319` chưa cập nhật: còn `thieu_buoc_in` (backend không còn phát),
  **thiếu hẳn** `thieu_buoc_chung` + `thieu_ke_hoach_buoc_chung` (backend phát ở
  `bai_ghep_service.py:1032, 1035`).
- `BaiGhepDetailView.tsx:335` dùng `LABELS[code] ?? code` → người dùng thấy chữ
  `• thieu_buoc_chung`. Đây là **trạng thái mặc định của mọi bài mới tạo**.
- **Kiểm**: đọc.

---

## §2. LỆCH PLAN — ĐÃ LÀM HẾT (8/8, đợt 4 · 2026-08-03)

| # | Đã làm gì |
|---|---|
| **K1** | Form bước chung nay có **vật tư** (chọn từ danh mục + định mức, sửa theo lô vì API là replace-all), **năng suất** + `chay_phut` (gõ đè thắng công thức), **canh máy · vệ sinh · chờ · di chuyển · số lượt chạy**, và khối **gia công ngoài đầy đủ** (NCC · đơn giá · SL gửi · hao hụt cho phép · ngày gửi/nhận · ngày vận chuyển/gia công · yêu cầu kỹ thuật). Backend trả thêm **giá trị hiện có** của mọi trường để form mồi lại được — không thì mở drawer là ô trống rồi lưu đè mất số cũ. Kèm `useEffect` reset form khi đổi bước chung. **`khoan_json` vẫn CHƯA có UI** (cần editor riêng kiểu `KhoanRatesEditor`) — ghi nợ ở §3 |
| **K2** | `canh_bao_cua` bỏ `khac_giay` · `khac_so_mau` · `khac_so_mat` · `bai_thua`; gỡ luôn hằng `FILL_THAP` và chỗ tô đỏ "Tờ dùng" ở header. **Giữ** `co_gap` · `lech_han` · `don_huy` · `thanh_vien_khong_san_sang` — đó là tín hiệu TRẠNG THÁI đơn/lệnh, không phải phán đoán quy cách; plan chỉ liệt kê bỏ nhóm quy cách/bình bài. Bảng "Kiểm tương thích" vẫn bày đủ giá trị để người tự so |
| **K3** | `phan_giay_to` + `ty_le_giay` chia theo **`cai_moi_to`** từng thành viên, trả ở cả `so_do` lẫn `detail_dict`, hiện thành chip trên thẻ lệnh. Tờ dùng chung nên không có "tờ của lệnh nào" — chia được là CHI PHÍ giấy theo diện tích chiếm trên tờ |
| **K4** | Ô `con/tờ` **sửa tại chỗ** trên thẻ lệnh (Enter lưu · Esc huỷ · blur lưu), đẩy lên cha qua `onSuaCon` — sơ đồ vẫn KHÔNG tự gọi API ghi |
| **K5** | `_do_thi_cua` **đóng bao theo cạnh**: lặp kéo thêm lệnh cho tới khi không còn cạnh trỏ ra ngoài, thay vì lọc `order_id` một bậc. Bìa của đơn này chờ ruột của đơn kia (khách gộp đơn) nay không bị cắt mất cạnh |
| **K6** | Backend cấp cờ **`da_lap_ke_hoach`** thật; FE bỏ hẳn `!thieu.includes("Chưa chọn tổ")`. Nút sửa/tách chuyển sang **hiện khi hover** (giữ khi focus-within cho bàn phím, luôn hiện trên cảm ứng) |
| **K7** | Vẽ **cạnh chéo lệnh trong cùng bài** (dây tím đứt nét, kèm `<title>`), tách khỏi nhánh "tiền nhiệm ngoài bài" (dây xám). Trước đây chỉ vẽ loại ngoài bài nên cạnh giữa hai thành viên biến mất dù engine vẫn tính |
| **K8** | Thêm `BaiGhepVongPhuThuoc` mang `nut` + `nhan_chung` + `tu_tro`; router trả 409 với `detail` là **object** (`message` · `loai` · `nut` · `tu_tro` · `nhan_chung`) thay vì một chuỗi |

**Sửa kèm trong đợt này:** **M1** (select tổ so id thay vì tên — gốc là backend chỉ trả `to_ten`, nay trả cả `department_id`/`may_id`) và **M10** (`BaiGhepListItem.hao_in_de_xuat` → `hao_de_xuat` + `so_buoc_chung`, cùng lỗi schema-nuốt-field như S2). Nhãn "Vào/Ra/Hao cả lượt" trong drawer thôi đóng đinh chữ "tờ", lấy theo đơn vị đã khai; `nhanDonVi` export ra dùng chung thay vì chép đôi.

<details><summary>Chẩn đoán gốc (giữ để tra lại)</summary>

| # | Plan nói | Thực tế lúc review | Kiểm |
|---|---|---|---|
| K1 | §6: form bước chung có **vật tư & định mức** và **công việc khoán** | `BuocChungForm` (`BaiGhepSoDo.tsx:583-756`) không có cả hai. Backend nhận `vat_tus` + `khoan_json`, có bảng `bai_ghep_cong_doan_vat_tu`, `_thay_vat_tu_chung()` đã viết — nhưng không có ô nhập nào, bảng vật tư sẽ luôn rỗng. Form bày **6/23** trường (xem §2b) | đọc |
| K2 | "Cảnh báo còn lại — đúng hai": bỏ *khác quy cách*, *bình lệch tỷ lệ* | `canh_bao_cua` (`bai_ghep_service.py:1043-1079`) **không sửa một dòng nào** so với `11a0152`. Vẫn phát `khac_giay`, `khac_so_mau`, `khac_so_mat`, `bai_thua`. FE vẫn tô đỏ "Tờ dùng" khi `fill_pct < 55` (`BaiGhepDetailView.tsx:313-316`). Chỉ có "vượt khổ 107%" là gỡ thật | probe (`canh_bao = ['bai_thua']`) |
| K3 | §3 + §9: `so_do` trả **phần giấy từng lệnh**; thẻ in hiện số đó | Không có trường nào, không backend không FE. CSS `.bgsd-card-in__badge--giay` còn nằm chết ở `bai-ghep.css:1399` | đọc |
| K4 | §2: đầu hàng là thẻ lệnh có ô `con/tờ` **sửa tại chỗ** | `BaiGhepDagCanvas.tsx:738-740` là `<span>` chỉ đọc. Sửa con/tờ phải mở modal (`BaiGhepSoDo.tsx:343-379`) | đọc |
| K5 | §2: tập node **lan theo cạnh chéo lệnh**, không bó trong bài | `_do_thi_cua` (`bai_ghep_service.py:386-408`) lan theo `order_id`, **một bậc**, không đóng bao theo cạnh. Cạnh vượt đơn bị `where(buoc_truoc_id.in_(...), buoc_sau_id.in_(...))` cắt sạch. Trong khi `so_do` dựng node `ngoai` (`:822-832`) **không** giới hạn đơn → hai chỗ nhìn hai phạm vi khác nhau | đọc |
| K6 | §4: **rê chuột** thẻ chung → nút Tách; §8 hỏi xác nhận khi đã lập kế hoạch | Nút Tách hiện thường trực. Điều kiện hỏi xác nhận **dò chuỗi tiếng Việt**: `const daLapKeHoach = !g.thieu.includes("Chưa chọn tổ")` (`BaiGhepDagCanvas.tsx:409`) → đổi câu chữ trong `_thieu_buoc_chung` (Python) là FE lặng lẽ tách. Ai đã khai máy + năng suất + ghi chú nhưng **chưa chọn tổ** → mất hết kế hoạch, không hỏi một câu | đọc |
| K7 | §4: cạnh chéo lệnh giữ nguyên | Cạnh chéo giữa hai lệnh **trong cùng bài** không được vẽ: `so_do` chỉ đẩy vào `ngoai` các tiền nhiệm `not in trong_so_do` (`:822-824`), còn canvas chỉ nối tuần tự theo mảng (`BaiGhepDagCanvas.tsx:569-585`) | đọc |
| K8 | §3: sinh vòng → 409 **kèm chu trình và nhân chứng** | 409 đúng (`routers/bai_ghep.py:67`) nhưng chỉ trả `detail` là chuỗi; `Vong.nut` / `Vong.nhan_chung` không lên API dưới dạng cấu trúc | đọc |

### §2b. Trường backend nhận mà FE không có ô nhập (17 + vật tư)

`_SUA_DUOC_BUOC_CHUNG` + `BuocChungUpdateIn` có 23 trường + `vat_tus`.
`BuocChungForm` chỉ có: `department_id`, `may_id`, `so_nhan_cong`, `chay_phut`, `ghi_chu`,
`nha_cung_cap`, `don_gia_gia_cong`.

**Thiếu ô nhập**: `loai_buoc`, `khoan_json`, `nang_suat`, `don_vi_nang_suat`, `setup_phut`,
`ve_sinh_phut`, `cho_phut`, `di_chuyen_phut`, `so_luot_chay`, `sl_gui`, `ngay_gui_dk`,
`van_chuyen_ngay`, `gia_cong_ngay`, `ngay_nhan_dk`, `hao_hut_cho_phep`, `yeu_cau_ky_thuat`,
**`vat_tus`**.

Đáng chú ý: `setup_phut` / `ve_sinh_phut` không nhập được nhưng `thoi_luong_buoc(c)` **vẫn cộng
chúng** vào `tong_phut` hiện trên thẻ → thời lượng lượt chung luôn thiếu makeready + rửa mực.

</details>

---

## §3. TRUNG BÌNH — ĐÃ LÀM HẾT (10/10, đợt 7 · 2026-08-04)

| # | Đã sửa thế nào | Test khoá |
|---|---|---|
| **MỚI** `khoan_json` | Form bước chung nay có ô **Công việc khoán** — dùng lại **nguyên** khối `khsx-khoan-card` của drawer bước lệnh. Backend **bỏ nhận `khoan_json` thô**, chuyển sang `piece_rate_id`: ảnh chụp đơn giá là thứ SERVER chụp, cho client gửi thẳng là mở cửa cho đơn giá bịa chảy vào phiếu lương. `_ghim_khoan_chung` gọi thẳng `LsxService._dau_viec_cua_cong_doan` + `khoan_snapshot` + gắp định mức (năng suất · số người), `_khoan_chung_dict` trả thêm phần dẫn xuất bằng `_khoan_derived` — quy cách truyền `{}` CÓ Ý, vì tờ ghép không thuộc quy cách của lệnh nào, thiếu cầu thì báo `khoan_thieu` chứ không mượn số của một thành viên bất kỳ | `test_khoan_luot_chung_ghim_theo_id_va_chan_dau_viec_la` — ghim đúng ảnh chụp, kéo theo định mức (hết chip "Chưa có năng suất"), và đầu việc **không thuộc tổ → chặn** |
| **M2** | Thêm `sapHang()`: xếp thành viên của cùng một lượt chung **nằm liền nhau**, nên thẻ chung không còn trải qua nhánh lạ. Ba lượt chung đan chéo thì xếp liền là bất khả → cửa chặn thứ hai trong `initialPositions`: thẻ nào còn nằm trong vùng thẻ chung mà không phải thành viên thì **đẩy sang phải**. Để chồng là thẻ dưới biến mất, không ai biết bước đó tồn tại | — (layout) |
| **M3** | Bỏ điều kiện `i === indexOf(toả)+1`. Neo mới = **thẻ riêng ĐẦU TIÊN sau điểm toả** (bước ngay sau mà cũng bị gộp thì nhảy tiếp). Không có thẻ nào — bước gộp là bước CUỐI routing, rất hay gặp — thì chip dồn về khối tổng kết cuối nhánh, xếp trên "dư con": hai số cùng là tổng kết, đọc liền nhau đúng thứ tự tờ → con | — (layout) |
| **M4** | Hai cột hao thành **nullable**: `NULL` = chưa khai (dùng hao máy đề xuất) · `0` = khai "chạy đúng số, không bù". Migration **`0152`** đưa bài đang 0/0 về NULL để **giữ nguyên số đang hiện**. FE: ô để trống ≠ gõ 0, kèm placeholder + dòng nhắc "đang dùng hao máy đề xuất N tờ" | `test_khai_hao_0_thi_bai_khong_tu_thay_bang_de_xuat` — cả ba trạng thái NULL → 0 → NULL |
| **M5** | `tong_to` nay cũng dùng `hao_ap_dung` như `to_nguyen_can`. **Lòi thêm một lỗi**: hao cộng SAU phép chia mảnh xả, tức đếm hao bằng tờ nguyên — tờ xả 4 mảnh thì 100 tờ hao bị đòi thành 400 mảnh. Sửa thành `ceil(tong_to / xa)` | `test_tong_to_va_to_nguyen_can_dung_chung_mot_co_so_hao` — chạy qua cả ba trạng thái hao |
| **M6** | `_do_thi_cua` thêm **cạnh NGẦM theo `thu_tu`** trong từng lệnh. `lsx_cong_doan_phu_thuoc` chỉ lưu cạnh NGƯỜI nối tay (thường là cạnh chéo lệnh); chuỗi trong một lệnh là ngầm — đúng chuỗi `_ap_chuoi_nguoc` đi. Kèm lợi ích: `kiem_gop` chặt hơn đúng chỗ cần — gộp chéo (A2+B3 khi B2+A3 đã gộp) nay lộ ra là vòng thật | `test_thu_tu_buoc_chung_dung_chieu_du_routing_khong_co_canh` — assert trước rằng routing **không có cạnh nào**, rồi gộp ngược chiều |
| **M7** | `replace_routing` gọi thêm `_bai_ghep_xep_lai(lsx)` (import trễ, ngược chiều với `BaiGhepService._lsx_svc`) → `_sap_lai_thu_tu` + `_tinh_lai` | `test_sua_routing_thi_thu_tu_buoc_chung_duoc_danh_lai` — đảo routing cả hai lệnh, thứ tự bước chung phải đảo theo |
| **M8** | Tính tập chọn mới **NGOÀI** updater của `setDangChon` (StrictMode chạy updater 2 lần → 2 request mỗi cú bấm). Thêm **seq token**: chỉ lượt hỏi mới nhất được ghi `ungVien`; `huyChon` bump seq nên câu trả lời đang bay về không sáng lại thẻ nào | — (hành vi FE) |
| **M9** | Bấm thẻ mờ vì sinh vòng nay **hiện lý do server trả** ngay trên thanh chọn (`role="alert"`), thay vì `return` câm | — (hành vi FE) |
| **M12** | `tinhCot` trả `{cot, hoiTu}`; hết ngân sách mà còn đổi → toolbar hiện chip **"Sơ đồ xếp chưa chuẩn"** thay vì lặng lẽ bày layout sai. Và hàm nay **có đọc `phu_thuoc_step_keys`**: cạnh chéo lệnh cũng đẩy cột, nên "bìa chờ ruột" không còn vẽ dây chạy ngược | — (layout) |
| ~~M1~~ · ~~M10~~ | ✅ đã sửa từ đợt 4 | — |

<details><summary>Chẩn đoán gốc (giữ để tra lại)</summary>

| # | Chỗ | Vấn đề |
|---|---|---|
| **MỚI** | `BaiGhepSoDo.tsx` `BuocChungForm` | `khoan_json` chưa có ô nhập — backend nhận, model có cột, nhưng form không bày. Công việc khoán của lượt chung sẽ luôn rỗng |
| M2 | `BaiGhepDagCanvas.tsx:208-215`, `:235-244` | Thẻ chung đặt tại `y = min(hàng)`, cao `(max-min)*ROW_H + CARD_H`. Bài 3 lệnh mà chỉ hàng 0 và 2 gộp → thẻ chung **phủ đè** thẻ bước của hàng 1 ở cùng cột |
| M3 | `BaiGhepDagCanvas.tsx:843` | Chip "dư tờ" chỉ render ở bước **ngay sau** điểm toả. Nếu bước gộp cuối cũng là bước cuối routing (rất phổ biến khi mới gộp bước in) thì **không có chip nào**, dù `du_to > 0`. Probe: `du_to = 1075` mà canvas im |
| M4 | `bai_ghep_service.py:710` | `hao_ap_dung = int(setup) + int(chay) or int(hao_de_xuat)` — người dùng cố ý khai hao = 0 bị âm thầm thay bằng số máy đề xuất. Không có cách khai "không hao" |
| M5 | `bai_ghep_service.py:700` vs `:720` | `tong_to` chỉ cộng hao **thủ công**, `to_nguyen_can` cộng `hao_ap_dung` (có fallback). Hai số cùng nghĩa "tờ phải cấp" nhưng hai cơ sở hao khác nhau |
| M6 | `bai_ghep_service.py:577-601`, `:895-902` | `_sap_lai_thu_tu` chạy đúng khi routing **có** cạnh `LsxCongDoanPhuThuoc`. Khi routing **không có cạnh** (bước thêm tay chưa nối dây) → đồ thị rỗng → Kahn trả thứ tự tuỳ ý (probe ra `In(0) · CTP(1) · Cán(2)` — sai chiều). `_node_chungs` chạy ngược theo đúng thứ tự sai đó để chia hao. **Không guard, không test** |
| M7 | không có chỗ nào | `_sap_lai_thu_tu` chỉ gọi trong `gop`/`tach`. **Đổi thứ tự routing của lệnh** (`replace_routing` chặn xoá bước bị đè nhưng cho phép đổi `thu_tu` và cả `cong_doan_id`) không kích hoạt sắp lại → `thu_tu` bước chung thiu, bất biến "các bước gộp cùng một công đoạn" có thể vỡ âm thầm |
| M8 | `BaiGhepDagCanvas.tsx:372-387` | `capNhatUngVien()` (fetch + `setUngVien`) gọi **bên trong updater của `setDangChon`**. `main.tsx:11` bật StrictMode → updater chạy 2 lần → **2 request `POST /ung-vien-gop` mỗi lần bấm**. Không có AbortController / seq token: bấm nhanh thì response cũ về sau ghi đè `ungVien` của tập chọn mới → thẻ sáng sai → bấm Gộp bị 409, đúng cái mà "kiểm TRƯỚC" định tránh. (Không phải stale-closure: `ungVien` nằm trong dep array) |
| M9 | `BaiGhepDagCanvas.tsx:380` | Bấm thẻ mờ **vì sinh vòng** → `return truoc`, không phản hồi gì. Plan §4 nói "Bấm thẻ mờ = bắt đầu chọn lại từ công đoạn đó". Thẻ mờ vì khác công đoạn thì đúng, thẻ mờ vì vòng thì câm |
| M12 | `BaiGhepDagCanvas.tsx:76-105` | `tinhCot` **có dừng** (giá trị chỉ tăng, chặn trên bởi `tongBuoc`) nên không vòng vô tận. Nhưng ngân sách `tongBuoc+1` vòng là *chặn cứng chứ không phải chứng minh hội tụ*; nếu chưa hội tụ, hàm im lặng trả layout mà các bước cùng nhóm **không cùng cột** → thẻ chung vẽ đè. Không có cờ báo. Hàm cũng bỏ qua hoàn toàn `phu_thuoc_step_keys` (chỉ dùng thứ tự mảng) |

</details>

---

## §4. LỖ ĐỘ PHỦ TEST — ĐÃ LẤP HẾT (4/4, đợt 8 · 2026-08-04)

| # | Đã lấp thế nào |
|---|---|
| **1** | M6 nay có `test_thu_tu_buoc_chung_dung_chieu_du_routing_khong_co_canh` (đợt 7) — assert TRƯỚC rằng routing không có cạnh phụ thuộc nào, rồi gộp ngược chiều và bắt thứ tự bước chung phải đúng chiều |
| **2** | `test_do_thi_cua_lan_theo_canh_qua_NHIEU_bac_khong_dung_o_mot_hop` — dây chuyền A(trong bài) → C → D, cả C lẫn D đều ngoài bài, D cách bài **hai bậc**. Kiểm cả node lẫn cạnh, và cờ `trong_bai`. **Đã chứng minh đỏ được**: chặn vòng lặp ở một bậc thì `d.id` rơi khỏi tầm ngắm |
| **3** | `test_canh_cheo_lenh_lam_vo_phep_gop_o_TANG_SERVICE` — A.In chờ B.Cán (cạnh khai qua API thật), gộp A.In+B.In phải ra `BaiGhepVongPhuThuoc` có `nut` + `nhan_chung`; `ung_vien_gop` phải trả `gop_duoc=False` kèm lý do. Kết đuôi bằng ca NGƯỢC: gỡ cạnh đi thì chính phép gộp ấy chạy ngon — chứng minh đỏ là DO cạnh chứ không do test dựng sai. **Đã chứng minh đỏ được**: bỏ nạp cạnh thì `gop_duoc` trở lại `True` |
| **4** | Dựng **vitest + jsdom + testing-library** (repo trước nay không có bộ chạy test FE nào). `BaiGhepDagCanvas.test.tsx` render canvas thật rồi bấm vào nó: một-cú-bấm-một-request dưới StrictMode · câu trả lời cũ về muộn bị bỏ · thẻ mờ vì vòng phải nói lý do · chip dư tờ khi bước gộp là bước cuối · `sapHang` xếp liền nhau · `tinhCot` đọc cạnh chéo và báo chưa hội tụ. **Ba cái đầu đã chứng minh đỏ được** bằng cách hạ tạm code về bản cũ. `npm test` nối vào cổng kiểm CI, và pytest có `test_bang_chung_fe_that_su_ton_tai` chốt "file test còn đó + CI còn gọi nó" |

Test grep chuỗi cũ **giữ nguyên** — nó rẻ và bắt được đúng một loại lỗi (ai đó gỡ mất một cửa ghi
mà không để ý). Chỉ khác là nó thôi làm bằng chứng DUY NHẤT; docstring đầu file đã ghi rõ ranh giới.

> Còn nợ ngoài phạm vi §4: plan §Verification mục 3 (đối chiếu số bằng engine thật trên `GB26-0001`
> của DB dev) **không có dấu vết đã làm**; mục 6 (soi UI trên trình duyệt) **chưa làm**.

---

## §5. CÒN — VẶT (6)

1. **CSS chết**: `.bgsd-card-in*` — khối `bai-ghep.css:423-511` + `:1399`, **không TSX nào dùng**
   (grep toàn repo chỉ ra file CSS). Mục "Dọn" của plan bỏ sót.
2. **Nhãn chết**: `thieu_buoc_in` trong `client.ts:317` — backend không còn phát.
3. **Docstring nói dối**: `routers/bai_ghep.py:119` vẫn ghi *"Đồ thị của bài: N nhánh vào → MỘT
   node IN → N nhánh ra"*, trỏ `docs/spec-bai-ghep-dag.md §2.1` — chính mô hình lát này xoá bỏ.
   `docs/spec-bai-ghep-dag.md:91, 276` cũng còn tả `buoc_in_step_key` như thiết kế sống.
4. `_co_cong_doan_in` (`bai_ghep_service.py:196-197`) vẫn gác cửa vào bài: bài chỉ định gộp CTP
   vẫn bắt **mọi lệnh phải có bước in**.
5. `bai_ghep_service.py:900`: nhánh `else` của `if pct < 100` là code chết — `_hao_o_bac` đã kẹp
   `pct ≤ 99`.
6. `thieu_cua` không kiểm `bg.may_id` → bài "sẵn sàng" vẫn đẻ dòng lịch `may_id=None` (probe xác
   nhận). Kèm: `_node` (`:974-977`) `db.get` mỗi cạnh → N+1 (có sẵn từ trước lát này).

---

## Nhận xét

Cụm S2–S5 đều là **chỗ nối ra ngoài module** — response schema của lệnh, xếp lịch, vòng đời thành
viên. Phần lõi (đồ thị co, kiểm vòng, lượt đi/lượt về, chuyển tầng hao) làm kỹ và có test tử tế;
nhưng bộ test 1125-pass **không phủ phần rìa**, nên "test xanh" không nói lên gì về năm lỗi nặng
đó. Lấy màu xanh đó làm bằng chứng cho toàn bộ là sai lầm phán đoán.

Rút ra cho lát sau: mỗi lần đổi hình dạng dữ liệu, phải đi hết **bốn mối** — service trả gì ·
response model khai gì · ai ĐỌC cột đó · vòng đời (thêm/bỏ/xoá) có dọn không. Bốn lỗi nặng đúng
là bốn mối đó.

## Đã quyết là KHÔNG làm (2026-08-03)

- **Ghép bài theo TỪNG TAY** — tay 1 của sách A chung tờ với tay 1 của sách B. Đúng thực tế nhất,
  nhưng phải đổi mô hình thành viên từ *một lệnh* sang *một tay của lệnh*. Người dùng chốt **tạm
  thời chưa làm**; hiện ruột sách bị chặn khỏi bài ghép (đợt 6), bìa sách vẫn ghép bình thường.

## Còn lại — đề xuất thứ tự

> Mục này từng liệt K1 · M1 · M10 · K2 · K3 · K4 là việc phải làm trong khi §0/§2 ghi cả sáu đã
> xong — đọc lướt là hiểu sai trạng thái. Đã viết lại theo đúng những gì còn nợ.

1. **§5 mục 6** — `thieu_cua` không kiểm `bg.may_id` → bài "sẵn sàng" vẫn đẻ dòng lịch
   `may_id = None`. Cái này ra tận bàn xếp lịch, là mục duy nhất còn lại có hậu quả thật.
2. **§5 mục 4** — `_co_cong_doan_in` vẫn bắt MỌI lệnh phải có bước in, kể cả bài chỉ định gộp CTP.
3. **§5 mục 1 · 2 · 3 · 5** — dọn code/nhãn/docstring chết.
4. Ngoài sổ này: đối chiếu số trên DB dev thật (`GB26-0001`) và soi UI trên trình duyệt — hai mục
   Verification của plan chưa làm.
