# Sản xuất CHỈ ghi số lượng · Bàn tổ trục LỆNH · Mẻ đủ chi tiết · Màn thợ — Thiết kế

**Ngày chốt:** 11/09/2026
**Phạm vi:** Kế hoạch SX (lệnh) · Bài ghép · Phát hành SX (snapshot) · Thực hiện SX (bàn tổ) ·
Đóng nhóm thành phẩm · seam Bảng lương.

---

## 1. Quyết định gốc của chủ xưởng

> *"Bên sản xuất với kế hoạch thì không cần liên quan tới lương khoán đâu, đó là việc của kế toán
> lương. Bên sản xuất chỉ ghi nhận số lượng thôi."* (11/09/2026)
>
> *"Tạm thời xoá cơ chế lương khoán từ kế hoạch đến sản xuất đi, bên kế hoạch vẫn chọn đầu việc
> chi tiết nhé."*

Ranh giới mới, một câu: **sản xuất + kế hoạch đo SỐ LƯỢNG; kế toán lương đổi số lượng ra TIỀN.**

Vì sao cơ chế cũ sai từ gốc — không phải sai ở một phép tính:

- Đơn giá bị **ghim lúc phát hành** (`khoan_json.don_gia`), trong khi giá thật phụ thuộc máy nào
  chạy, kíp mấy người, mấy màu mực của chính đơn đó, khuôn cũ hay mới, thùng mấy lớp. Kế hoạch lên
  *máy A kíp 2 người*, xưởng chạy *máy B kíp 3 người* — số lượng vẫn đúng, tiền thì sai.
- Không engine nào suy được các chiều đó. Xưởng đã mã hoá sẵn chúng trong **mã đầu việc** của họ,
  và người đọc mã đó là kế toán lương, không phải máy.
- Hệ quả trong code: `phan_bo._tinh_batch` làm `kq.q_pay = kq.q_native` (quy đổi đồng nhất) nên
  đơn giá *đ/nhịp* hay *đ/m²* bị nhân thẳng vào **số tờ**; tầng lệnh thì lại đi qua `tien_khoan` +
  cầu quy đổi + công thức. Hai tầng ra hai số tiền khác nhau cho cùng một mẻ.

Nên bản này **gỡ tiền**, giữ **số lượng** và giữ **đầu việc** kế hoạch đã chọn.

## 2. Bốn nguyên tắc

1. **Sản xuất không có ô tiền nào.** Không đơn giá, không thành tiền, không thưởng/phạt tính bằng
   tiền — kể cả ô chỉ-đọc. Có ô tiền là có người đối chiếu, có người đối chiếu là có tranh chấp về
   một con số hệ không chịu trách nhiệm.
2. **Đầu việc thì GIỮ.** Kế hoạch vẫn chọn đầu việc chi tiết của tổ; ảnh chụp vẫn ghim `rate_id` +
   tên. Đó là **cái tên của việc**, không phải cái giá của việc — kế toán lương cần đúng nó để tra
   bảng giá tại thời điểm tính lương.
3. **Định mức thì GIỮ nguyên vẹn.** Năng suất người-giờ, số người tối thiểu/tiêu chuẩn/tối đa,
   `cong_thuc_gio`, đơn vị năng suất — xếp lịch và thời lượng bước sống bằng chúng. Gỡ chúng là
   đánh sập Xếp lịch 2/3.
4. **Bản ghi của bàn tổ là LỆNH (hoặc BÀI GHÉP), không phải công đoạn rời.**
   *"Lệnh hoặc bài ghép thôi, chứ không làm sao tôi biết được công đoạn đó cho lệnh nào."*

## 3. Gỡ tiền khoán khỏi kế hoạch → sản xuất

### 3.1 Cột bỏ đi

| Bảng | Cột | Vì sao |
|---|---|---|
| `san_xuat_phan_bo` | `don_gia` | đơn giá đóng băng của header phân bổ |
| `san_xuat_phan_bo_dong` | `don_gia` | đơn giá của từng dòng người |
| `san_xuat_phan_bo_bu_tru` | `don_gia` | đơn giá của dòng bù trừ |

Ba cột này là **toàn bộ** đường tiền ở tầng sản xuất. Bỏ chúng thì `_don_gia_don_vi`,
`don_gia_hd`, `don_gia_hieu_dung` mất chỗ chảy về, và tự nhiên phải gỡ theo.

**Không** bỏ `q_tra_luong` / `so_luong_tra_luong` / `q_ban_dia`: đó là **sản lượng theo người**,
thứ duy nhất kế toán lương cần nhận. Tên cột mang chữ "trả lương" nghe lệch nhưng đổi tên ba cột
xuyên 6 file để đẹp chữ là churn — docstring nói rõ nghĩa là đủ.

`san_xuat_thuong_to_truong` (bảng) — **xoá bảng**. Nó là bảng TIỀN thuần: `tien_khoan`,
`rate_pct`, `so_tien`.

`payroll_lines.thuong_to_truong` (cột) — **giữ**. Đó là cột phía BẢNG LƯƠNG; bảng bậc thưởng
(`piece_leader_bonus_brackets`) cũng là cấu hình lương. Màn "Khoán theo kỳ" của kế toán sẽ rót
lại vào đúng cột này. Tạm thời cột về 0.

### 3.2 Ảnh chụp `khoan_json` — giữ tên việc, bỏ giá

Sau bản này `khoan_json` ghim vào bước (`lsx_cong_doan`, `bai_ghep_cong_doan`,
`san_xuat_cong_viec`) còn đúng các khoá:

| Khoá | Giữ? | Vai |
|---|---|---|
| `rate_id` · `ten` | **giữ** | tên đầu việc kế hoạch đã chọn — cửa của kế toán lương |
| `don_vi` · `don_gia` | **bỏ** | đơn vị TIỀN + đơn giá |
| `cong_thuc` | **bỏ** | công thức RA TIỀN của đầu việc |
| `don_gia_hd` | **bỏ** | đơn giá hiệu dụng (thêm 08/09/2026, nay vô nghĩa) |
| `nang_suat_nguoi_gio` · `don_vi_nang_suat` · `cong_thuc_gio` | **giữ** | thời lượng bước |
| `so_nhan_cong_toi_thieu` / `_tieu_chuan` / `_toi_da` | **giữ** | kíp người |

Ảnh chụp CŨ vẫn còn khoá tiền trong JSON — **không migrate, không xoá**. Code thôi đọc chúng là
đủ; JSON không có schema nên khoá mồ côi vô hại, còn viết migration bò qua ba bảng JSON chỉ để
làm sạch mắt là rủi ro không đổi được gì.

### 3.3 Danh mục thì KHÔNG đụng

`piece_rates` (mã · tên · đơn vị · đơn giá · công đoạn), `cong_doan_dau_viec.cong_thuc_khoan`,
`piece_leader_bonus_brackets`, chip `don_gia_khoan` trong ô công thức của danh mục — **giữ hết**.
Đây là bảng giá của kế toán lương. Bản này chỉ ngắt đường *danh mục → lệnh → sản xuất → lương*,
không phá bảng giá.

### 3.4 Hàm/khối gỡ ở backend

| File | Gỡ |
|---|---|
| `services/san_xuat/phan_bo.py` | `_don_gia_don_vi`; `kq.don_gia`; khoá `"don_gia"` trong dòng; `header.don_gia`; `don_gia` của `bu_tru` |
| `services/san_xuat/snapshot.py` | khối gắn `don_gia_hd` + service trễ `_DonGiaHieuDung` |
| `services/lsx_service.py` | `don_gia_hieu_dung`, `_khoan_derived`, `_khoan_tu_kh`, khoá `khoan` của `xem_truoc_buoc`, `khoan_*` trong payload bước |
| `services/piece_work_service.py` | `khoan_snapshot` chỉ còn `{rate_id, ten}` |
| `services/san_xuat/thuong_to_truong.py` | XOÁ FILE |
| `repositories/thuong_to_truong_repo.py` | XOÁ FILE |
| `models/san_xuat_thuong_to_truong.py` | XOÁ FILE (+ export ở `models/__init__.py`) |
| `repositories/production_output_repo.py` | `unit_price` luôn `0.0` + docstring nói rõ cột `khoan` = 0 tới khi có màn kế toán |
| `services/bien_cong_thuc.py` | biến `don_gia_khoan` chỉ còn nguồn DANH MỤC (bỏ nhánh đọc `khoan_json`) |

### 3.5 Hệ quả phải nói trước

- `payroll_lines.khoan` và `.thuong_to_truong` **về 0 cho mọi người** cho tới khi dựng màn
  *"Khoán theo kỳ"* của kế toán lương (pha sau, ngoài bản này).
- `docs/CONG_THUC_TINH_LUONG.md` §6.1 nói `khoan` luôn = 0 — câu đó **đúng lại** sau bản này;
  sửa lý do trong doc chứ không sửa kết luận.

## 4. Bàn tổ đổi trục sang LỆNH / BÀI GHÉP

### 4.1 Ba tầng

```
LỆNH SX (hoặc BÀI GHÉP)            ← bản ghi, mỗi lệnh MỘT dòng
└── công đoạn CỦA TỔ trong lệnh    ← chỉ bước thuộc tổ đang mở bàn
    └── MẺ (batch)                 ← trong drawer của bước
```

Bài ghép là **một dòng duy nhất**, không xẻ ra theo từng lệnh thành viên: bài ghép chạy một lần
trên một tờ, tổ nhìn nó là một việc.

### 4.2 Sắp thứ tự + phân trang

- Sắp mặc định: **giờ dự kiến của bước SỚM NHẤT của tổ trong lệnh đó**, lệnh chưa xếp giờ dồn
  cuối, rồi `nguon_ma`.
- **Phân trang + gom nhóm ở MÁY CHỦ**, đơn vị trang là **LỆNH** (không phải bước) — cắt trang
  theo bước thì một lệnh bị xé qua hai trang.
- Endpoint `GET /api/san-xuat/work-items` nhận thêm:
  `nhom=lenh|phang` (mặc định `lenh`), `trang` (1-based), `co_trang` (mặc định 20, tối đa 100).
- `nhom=phang` giữ đúng hình cũ (mảng `cong_viec` phẳng) + nhận `tu_ngay`/`den_ngay` để **Gantt**
  chỉ kéo đúng cửa sổ đang xem. Gantt là view thứ hai, giữ nguyên.

Hình trả về của `nhom=lenh`:

```jsonc
{ "team_id": 7, "nhom": "lenh",
  "trang": { "trang": 1, "co_trang": 20, "tong": 34 },
  "lenh": [
    { "nguon_loai": "lsx", "nguon_ma": "LSX26-0012", "nguon_ten": "Hộp bánh 500g",
      "lsx_id": 12, "bai_ghep_id": null,
      "som_nhat": "2026-09-11T07:30:00", "muon_nhat": "2026-09-11T15:00:00",
      "so_viec": 3, "digest": {"released":1,"running":1,"paused":0,"completed":1},
      "cong_viec": [ /* đúng hình `_item_dict` cũ, không đổi một khoá nào */ ] }
  ] }
```

Giữ nguyên `_item_dict`: mọi view hiện có (thẻ · danh sách · Gantt · drawer) đọc chung một hình
thẻ việc, đổi hình thẻ là sửa bốn chỗ cùng lúc.

## 5. Mẻ phải đọc được trọn vẹn

> *"Trên màn hình của mỗi tổ, tổ trưởng phải thấy được thông tin của từng mẻ và sản lượng các thứ
> — nói chung đầy đủ và chi tiết để sau này hỗ trợ kế toán lương."*

### 5.1 Sản lượng theo người LUÔN hiện

Hôm nay phần của mỗi người chỉ hiện **sau khi bấm "Tính phân bổ"**. Sai: tổ trưởng ghi mẻ xong là
phải thấy ngay ai được mấy tờ.

`_tinh_batch` đã là **hàm thuần không ghi DB** và `board.py` đã gọi nó cho mọi header chưa chốt.
Mở rộng đúng một bước: **mẻ chưa có header thì cũng gọi `_tinh_batch`** và trả ra dưới khoá
`chia_du_kien` (nháp). Không cột mới, không bảng mới.

Nhãn FE đổi: khối `PhanBoBlock` từ **"Phân bổ lương"** → **"Chia sản lượng"**; bỏ số *đơn giá*,
bỏ cột *Đơn giá*, bỏ thẻ *"theo công thức"*.

Cách chia giữ nguyên: **trọng số = phút chấm công hợp lệ × hệ số bậc**, làm tròn lớn-nhất-dư theo
milli-đơn-vị để Σ = Q đúng bằng sản lượng tốt.

> **Giả định đã nêu và chưa được phủ định:** bảng *Cán phủ* / *Tổ bồi* của xưởng ghi *"tỷ lệ nhóm
> tự phân chia và báo cho kế toán"*. Bản này **giữ cách engine chia**, chưa mở ô cho tổ trưởng gõ
> tỷ lệ tay. Mở ô đó là một đợt riêng (cần cột `ty_le_tay` + quyền + vết audit).

### 5.2 Những thứ mẻ phải mang theo

| Thông tin | Lấy từ | Cột mới? |
|---|---|---|
| Máy đã chạy mẻ | `san_xuat_phien_chay.may_id` của phiên GIAO cửa sổ mẻ | không |
| Kíp mấy người | đếm người trong `chia_du_kien` / `nguoi_tham_gia` | không |
| Giờ từng người | `phut_thuc_te` của dòng chia | không |
| Đầu việc kế hoạch | `khoan_json.ten` của bước | không |
| Giờ kết thúc | `batch.ket_thuc` (có sẵn, FE chưa hiện) | không |
| Ca | `work_shifts` (ca chứa `batch.bat_dau`, ưu tiên `ca_san_xuat`) | không |
| Nguyên nhân hỏng | `batch.mo_ta_loi` (có sẵn) | không |
| Sự cố dừng máy trong mẻ | phiên `loai_dong='tam_dung'` + `ly_do` giao cửa sổ mẻ | không |
| Quy cách / vật tư | `cv.quy_cach_json`, `cv.vat_tu_json` (có sẵn ở thẻ việc) | không |

**Không cột mới nào cho cả mục 5.** Mọi số đã nằm trong DB, chỉ là chưa ai nối ra mặt đọc.

*Vai chính/phụ* — **không làm bản này**: `san_xuat_khoang_tham_gia` không có trường vai, thêm nó
là thêm cột + ô chọn ở luồng Bắt đầu/Thêm người, mà chia sản lượng hiện không dùng vai (dùng bậc).

## 6. Màn của THỢ

> *"Công nhân thuộc tổ đó chỉ nhìn thấy LSX — sản lượng các thứ... mà mình làm."*

Cùng ba tầng của §4, khác ở ba chỗ:

1. Chỉ những **lệnh mà thợ đó có việc** (`_loc_viec_cua_tho` đã có, lọc TRƯỚC khi gom lệnh và
   trước khi phân trang — nếu không thì trang 1 có thể rỗng trong khi trang 3 đầy).
2. Trong mẻ: **chỉ dòng của chính mình** + giờ vào/ra của chính mình. Không thấy phần người khác,
   không thấy tổng chia của cả tổ.
3. Thêm **luỹ kế tháng của tôi**: `GET /api/san-xuat/toi/san-luong?nam=&thang=` → tổng sản lượng
   của chính mình theo từng đơn vị, gom từ dòng chia ĐÃ CHỐT. Không tiền.

Gác quyền: cơ chế cũ giữ nguyên — `_la_tho` = scope `own` và không phải `head_user_id` của tổ.
Endpoint `toi/san-luong` chỉ trả của **chính người gọi**, không nhận `employee_id` từ client.

## 7. Đổi dữ liệu

| Migration | Việc |
|---|---|
| `0296_bo_don_gia_khoi_phan_bo` | `DROP COLUMN don_gia` ở `san_xuat_phan_bo`, `san_xuat_phan_bo_dong`, `san_xuat_phan_bo_bu_tru` |
| `0297_bo_bang_thuong_to_truong` | `DROP TABLE san_xuat_thuong_to_truong` |

Best-effort từng câu theo đúng khuôn `_migrate_bo_cot_*` đang có trong `db_migrations.py` (SQLite
cũ từ chối `DROP COLUMN` → cột mồ côi vô hại vì model không map). Không Boolean nên không dính bẫy
`server_default "0"/"1"`.

`docs/DB_SCHEMA.md` sửa **cùng lúc** — guard test bắt.

**Dữ liệu mất:** các số `don_gia` đã ghim trong phân bổ đã chốt và các dòng thưởng tổ trưởng đã
ghi. Không khôi phục được sau khi migration chạy trên DB dev. Chấp nhận được vì (a) prod đang DB
trắng, (b) chính những số đó là số sai của cầu quy đổi đồng nhất.

## 8. Không làm (bản này)

- **Màn "Khoán theo kỳ"** của kế toán lương — đổi sản lượng theo người ra tiền. Pha sau. Đây là
  lý do `payroll_lines.khoan` tạm về 0.
- **Khoản không gắn sản lượng**: lên khuôn 50.000 / 80.000 đ mỗi lần, "máy hư / hết hàng"
  846.154 đ / 1.250.000 đ. Chúng thuộc màn kế toán ở trên, chưa có chỗ đứng.
- **Bù lỗ (sàn lương), thưởng vượt năng suất 40%, luật "tổ trưởng lấy 5% + nhóm tự chia"** của Cán
  phủ / Tổ bồi — chủ xưởng đã nói bỏ qua bù lỗ.
- **Ô tỷ lệ chia tay cho tổ trưởng** — xem §5.1.
- **Vai chính/phụ trong mẻ** — xem §5.2.
- **Cờ `departments.luong_khoan` chưa gác tiền** và **tiền khoán cộng phẳng lên lương giờ**: hai
  lỗi thật ở tầng lương, nhưng bản này làm `khoan` = 0 nên chúng ngủ. Ghi lại ở đây để đợt kế toán
  không quên.

## 9. Kiểm thử

**Backend** (pytest nhắm file, không chạy cả bộ):
`test_san_xuat_phan_bo.py` · `test_san_xuat_board.py` · `test_san_xuat_board_api.py` ·
`test_san_xuat_san_luong.py` · `test_san_xuat_dong_nhom.py` · `test_san_xuat_g5_tich_hop.py` ·
`test_khoan_api.py` · `test_khoan_dau_viec.py` · `test_db_schema_doc.py`.
XOÁ: `test_thuong_to_truong.py` · `test_migration_0266_thuong_to_truong.py`.

**Frontend:** `npx tsc --noEmit` + `ThsxCards.test.tsx` · `ThsxDanhSach.test.tsx` + bài mới cho
gom lệnh và cho khối "Chia sản lượng" (phải KHÔNG có chữ "đơn giá").

**Luồng UI thật** (bắt buộc trước khi báo xong, không thay bằng curl một bước nào): mở bàn tổ →
thấy danh sách LỆNH → bung một lệnh → chọn công đoạn → Ghi mẻ → thấy ngay bảng chia sản lượng
theo người kèm phút, KHÔNG có ô tiền nào → đăng nhập một tài khoản thợ → chỉ thấy lệnh mình làm,
trong mẻ chỉ thấy dòng của mình.
