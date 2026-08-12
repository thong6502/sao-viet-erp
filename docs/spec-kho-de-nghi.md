# Spec — Đề nghị kho & Phiếu nhập/xuất (Giai đoạn 1)

> Nguồn nghiệp vụ: `BRD - Module Kho.docx` (mục §1.5 nguyên tắc dữ liệu, §2.2–2.17 quy trình,
> §3.15–3.19 danh mục). Spec này CHỈ lấy phần đề nghị → phiếu → lô/giá → ngưỡng tồn.

## 1. Phạm vi

**Trong phạm vi:** Đề nghị nhập/xuất · Duyệt đề nghị · Phiếu nhập/xuất ứng theo đề nghị ·
Lô + giá theo lô · Ngưỡng tồn & cảnh báo đẩy realtime · In phiếu.

**Ngoài phạm vi (giai đoạn sau):** kiểm kê, điều chuyển, hàng lỗi/hủy, POD giao hàng, WIP,
đồng bộ MISA, QR.

**Rút gọn giai đoạn 1:** chỉ 2 loại phiếu (`NHAP` / `XUAT`) và 2 loại đề nghị. Đặc thù từng
nghiệp vụ (nhập mua, nhập TP sau SX, xuất cấp bù, xuất bảo trì…) ghi vào ô **Ghi chú**, chưa
tách loại phiếu riêng. Cột `loai_phieu` vẫn giữ trong model để sau mở rộng chỉ cần thêm giá
trị, không phải migration lại.

> Đánh đổi đã biết: ghi chú là text tự do nên báo cáo **không nhóm được theo nghiệp vụ**
> (chưa trả lời được "tháng này xuất cấp bù bao nhiêu"). Chấp nhận ở giai đoạn 1.

## 2. Hai màn hình, một bảng dữ liệu

| Màn | Ai dùng | Thấy gì |
|---|---|---|
| **Đề nghị kho** (`/kho/de-nghi`) | Tổ trưởng, SX, Mua hàng, Bảo trì | Đề nghị của mình/bộ phận mình. KHÔNG thấy tồn, giá, lô, vị trí |
| **Hộp yêu cầu kho** (`/kho/yeu-cau`) | Thủ kho, quản lý kho | Mọi đề nghị đã duyệt + tồn + lô + vị trí (giá tùy quyền) |

Hai màn dùng **chung bảng `stock_request`**, khác nhau ở bộ lọc + quyền hiển thị cột. Tách 2
bảng thật sẽ phải đồng bộ 2 chiều, sai chỗ nào là lệch số ngay.

## 3. Vòng đời đề nghị

```
Nháp → Chờ duyệt → Đã duyệt → Kho tiếp nhận → Đang chuẩn bị
                                   ↓
                       Đã cấp một phần → Hoàn tất
```

Nhánh phụ: `Từ chối` (người duyệt) · `Hủy` (người tạo, chỉ khi còn `Nháp`/`Chờ duyệt`).

- Người tạo sửa được khi `Nháp` / `Chờ duyệt`. Từ `Đã duyệt` trở đi **khoá** — muốn đổi phải
  hủy và tạo lại (BRD §1.5: phiếu đã duyệt không sửa trực tiếp).
- Mỗi lần đổi trạng thái **đẩy realtime** (badge + toast) cho cả hai phía, không bắt refresh.

## 4. Duyệt

**Kho KHÔNG duyệt.** Kho chỉ tiếp nhận đề nghị đã duyệt rồi cấp — BRD §2.6 b8, §2.8 b6,
§2.9 b5 đều ghi giống nhau: *"Kho tiếp nhận phiếu đã duyệt"*.

| Cấp | Ai | Khi nào |
|---|---|---|
| 1 | Tổ trưởng / Quản lý bộ phận **đề nghị** | Mặc định, mọi đề nghị |
| 2 | Quản lý SX / Kế toán / BGĐ | Leo thang có điều kiện |

Điều kiện leo thang cấp 2 ở giai đoạn 1 (đơn giản, chưa cần đủ hết):
- Vượt ngưỡng số lượng khai theo bộ phận
- Đề nghị đánh dấu "gấp / bất thường"

Giai đoạn sau bổ sung theo BRD: vượt định mức (§2.6), hủy/thanh lý (§2.14), giá trị lớn,
điều chỉnh tồn sau kiểm kê phải qua **Kế toán** trước (§2.16 b10–11), sửa giá sau nhập cần
quyền Kế toán (§3.19). Điều kiện leo thang nên khai bằng **dữ liệu** — BRD §3.17 đã có sẵn
`Có yêu cầu phê duyệt` + `Mức độ nghiêm trọng` trên danh mục Lý do.

## 5. Phiếu ứng theo đề nghị

Mỗi **dòng** đề nghị giữ 4 số: `SL đề nghị` → `SL duyệt` → `SL đã ứng` → `SL còn lại`.

- Phiếu tạo bằng cách **chọn đề nghị đã duyệt** → dòng tự đổ ra, khoá mã hàng, chỉ sửa số lượng.
- **1 đề nghị ↔ nhiều phiếu** (cấp nhiều đợt), `SL đã ứng` cộng dồn.
- **Chặn cứng: không cho ứng vượt `SL duyệt`.** Muốn thêm → tạo đề nghị mới (BRD §2.5 b8).
- Ứng đủ hết dòng → đề nghị tự chuyển `Hoàn tất`; còn dở → `Đã cấp một phần`.

**Mọi phiếu bắt buộc có đề nghị.** Luật này khớp BRD — mỗi loại phiếu đã có sẵn chứng từ
đề nghị đứng trước:

| Phiếu | Đề nghị đứng trước | BRD |
|---|---|---|
| Nhập mua từ NCC | Đề nghị mua bổ sung (đã duyệt) → PO | §2.17, §2.2 |
| Nhập thành phẩm sau SX | Yêu cầu nhập kho từ KCS (chỉ hàng đạt) | §2.3 b2 |
| Nhập BTP/WIP tạm lưu | Yêu cầu tạm lưu do tổ trưởng công đoạn tạo | §2.4 b2 |
| Nhập trả vật tư thừa | Đề xuất nhập trả do tổ SX tạo | §2.7 b2 |
| Nhập hàng khách trả | Biên bản xử lý hàng trả do KD tạo | §2.13 b2 |
| Xuất NVL cho SX | Nhu cầu vật tư theo kế hoạch SX đã duyệt | §2.5 b1 |
| Xuất cấp bù | Phiếu đề xuất cấp bù | §2.6 b2 |
| Xuất tiêu hao/CCDC | Đề xuất lĩnh vật tư | §2.8 b1 |
| Xuất phụ tùng bảo trì | Đề xuất xuất phụ tùng | §2.9 b2 |
| Xuất giao khách | Yêu cầu xuất kho từ Kế toán/KD | §2.11 b1 |

**Ba miễn trừ** (chứng từ nguồn là thứ khác, đều ngoài phạm vi giai đoạn 1): tồn đầu kỳ
(§2.1) · phiếu điều chỉnh sau kiểm kê (§2.16) · phiếu hủy/thanh lý (§2.14).

## 6. Lô & giá

**Mỗi lần nhập = một lô riêng, id riêng, giá riêng.** Không gộp lô kể cả trùng mã hàng,
trùng giá — gộp là mất tính đích danh.

> SP A nhập đợt 1 giá 100k → `LOT-A-260723-01`. Đợt 2 giá 200k → `LOT-A-260801-01`.
> Xuất 15 cái: 10 từ lô 1 + 5 từ lô 2 → giá vốn = 10×100k + 5×200k.

- **Tồn một mã hàng = tổng `sl_con_lai` các lô.** Không lưu con số tồn rời → không bao giờ lệch.
- **Xuất phải chỉ định lô**; một dòng ăn nhiều lô thì tách thành nhiều dòng phân bổ.
- Hệ thống gợi ý **FIFO** (FEFO nếu hàng có date), thủ kho sửa được — đích danh là quyết định
  cuối (BRD §3.19: phương pháp mong muốn là đích danh).
- **Thủ kho chọn lô nhưng không thấy giá**: danh sách lô hiện `mã lô · ngày nhập · SL còn ·
  vị trí`. Cột đơn giá/giá vốn gate bằng `can_view_cost`.

## 7. Ngưỡng tồn

Khai theo cặp *(mã hàng × kho)*. Tính trên **tồn khả dụng** (không phải tồn thực tế — hàng
chờ KCS / hàng lỗi không được tính, BRD §1.5).

| Ngưỡng | Ý nghĩa |
|---|---|
| `ngưỡng cận tồn` | Cảnh báo sớm — nhắc chuẩn bị đề nghị mua, chưa gấp |
| `ngưỡng tồn` (tối thiểu) | Phải mua ngay, có nguy cơ dừng sản xuất |
| `ngưỡng tối đa` | Trần — cảnh báo mua dư, hàng dễ quá date |

| Trạng thái | Điều kiện |
|---|---|
| 🔵 Dư tồn | > ngưỡng tối đa |
| 🟢 Đủ | giữa cận tồn và tối đa |
| 🟡 Sắp hết | ≤ ngưỡng cận tồn |
| 🟠 Cần mua gấp | ≤ ngưỡng tồn |
| 🔴 Hết | = 0 |

Mặc định khi khai: `cận tồn = ngưỡng tồn × 1.3` (sửa được). Về sau có lead time NCC thì đổi
thành `ngưỡng tồn + tiêu thụ_ngày × lead_time`.

Dùng lại đúng 5 trạng thái này ở **3 chỗ**, định nghĩa một lần:
1. **Đẩy nhắc realtime** cho người có quyền đề nghị khi rơi 🟡/🟠/🔴
2. **Đèn tín hiệu** ở màn đề nghị (không có con số)
3. **Dashboard kho** — chỉ số *"Vật tư dưới tồn tối thiểu"* (BRD §4.3.2 #6)

## 8. Người đề nghị không xem được kho — thì biết khi nào mà đề nghị?

Đảo chiều: **hệ thống đẩy xuống, người dùng không tự đi soi kho.**

**Đề nghị XUẤT** — trigger là *nhu cầu*, không phải tồn:
- Vào từ ngữ cảnh công việc (đơn hàng / công đoạn / máy). Người đề nghị biết mình **cần** bao
  nhiêu là đủ; "có đủ không" là việc của kho trả lời.
- Kho phản hồi bằng **trạng thái** chứ không bằng con số tồn: `Đủ` / `Cấp được một phần
  (đã duyệt N)` / `Hết hàng — đã chuyển Mua hàng`.

**Đề nghị NHẬP** — trigger là *cảnh báo hệ thống đẩy*:
- Tồn khả dụng rơi 🟡/🟠/🔴 → đẩy **thẻ nhắc realtime** tới người có `can_request`:
  *"Vật tư X cần bổ sung — đề xuất mua N"*. Bấm 1 nút thành đề nghị, không cần biết tồn hiện tại.
- Kho cũng chủ động bấm **"Yêu cầu đề xuất mua"** đẩy sang Mua hàng.

**Chọn mã hàng:** người đề nghị **tự chọn** qua ô tìm kiếm trên danh mục vật tư (thấy tên +
ĐVT, không thấy tồn/giá). Để mô tả tự do thì kho phải dịch tay, dễ sai mã.

**Số lượng:** chưa có bảng định mức nên giai đoạn 1 **gõ tay**, hệ thống gợi ý = trung bình
3 lần đề nghị gần nhất cùng mã hàng + cùng bộ phận (rule-based từ data sẵn có).

## 9. Phân quyền

### 9.1 Bốn cờ quyền mới cho module `kho`

Cờ dùng lại được: `can_read` · `can_create` (lập phiếu) · `can_approve` (duyệt) ·
`can_manage_price` (sửa đơn giá sau nhập) · `can_export`.

| Cờ mới | Nhãn trong ma trận | Gate cái gì |
|---|---|---|
| `can_request` | Tạo đề nghị nhập/xuất | Lập đề nghị. Tách khỏi `can_create` vì người đề nghị KHÔNG lập phiếu, còn thủ kho lập phiếu nhưng không đề nghị |
| `can_view_stock` | Xem số tồn | Có cờ → thấy con số. Không có → chỉ thấy **đèn tín hiệu** 5 màu (§7) |
| `can_view_cost` | Xem giá vốn & giá trị tồn | Ẩn cột đơn giá/thành tiền ở màn lô, phiếu, **và cả bản in**. BRD §1.5 |
| `can_set_threshold` | Khai ngưỡng tồn / cận tồn | Sửa 3 ngưỡng ở §7 — đổi ngưỡng là đổi toàn bộ hệ cảnh báo |

**In phiếu không tạo cờ riêng** — ai đọc được phiếu thì in được, tránh thêm dòng ma vào ma
trận. Bản in tự ẩn cột giá khi không có `can_view_cost`.

⚠️ 4 cờ này là **cột mới** trên bảng quyền → bắt buộc viết vào `backend/app/db_migrations.py`
với `server_default=false` (bool Python, **KHÔNG** phải `"0"`), và cập nhật `docs/DB_SCHEMA.md`
cùng lúc, nếu không `init.ps1` FAIL.

Nhãn + hint khai trong `frontend/src/components/PermissionMatrix.tsx` (hiện **chưa có** dòng
`kho:` trong bảng EXTRA).

### 9.2 Ma trận vai trò

| Vai trò | read | scope | create<br>(phiếu) | request | approve | view<br>_stock | view<br>_cost | manage<br>_price | set<br>_threshold | export |
|---|---|---|---|---|---|---|---|---|---|---|
| Thủ kho | ✓ | all | ✓ | – | – | ✓ | – | – | – | ✓ |
| Quản lý kho | ✓ | all | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | ✓ |
| Kế toán kho | ✓ | all | – | – | ✓ | ✓ | ✓ | ✓ | – | ✓ |
| Tổ trưởng SX | ✓ | own | – | ✓ | ✓ | – | – | – | – | – |
| NV sản xuất | ✓ | own | – | ✓ | – | – | – | – | – | – |
| QL sản xuất | ✓ | own | – | ✓ | ✓ | – | – | – | – | – |
| NV mua hàng | ✓ | own | – | ✓ | – | – | – | – | – | – |
| Giám đốc | ✓ | all | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

Đọc theo hàng thấy rõ 3 nguyên tắc tách vai của BRD: **thủ kho lập phiếu nhưng không duyệt** ·
**kế toán duyệt & thấy giá nhưng không lập phiếu** · **người đề nghị scope `own`, không thấy
tồn lẫn giá**.

⚠️ **Cần sửa quyền hiện có**: `Nhân viên sản xuất` và `Nhân viên mua hàng` trong
`backend/app/seed.py` đang là `kho: _read(SCOPE_ALL)` — tức người đề nghị **đang xem được
toàn bộ tồn kho**, ngược với thiết kế. Phải hạ xuống `SCOPE_OWN`.

### 9.3 Tài khoản test

6 tài khoản đã có sẵn trong `seed_kho_staff()` (mật khẩu = `default_user_password`):

| Username | Tên | Phòng ban | Vai trò |
|---|---|---|---|
| `thukho` | Trần Thủ Kho | Kho | Thủ kho |
| `qlkho` | Lê Quản Lý Kho | Kho | Quản lý kho |
| `ketoankho` | Phạm Kế Toán | Kế toán | Kế toán kho |
| `nvsx` | Ngô Sản Xuất | Sản xuất | Nhân viên sản xuất |
| `qlsx` | Vũ Quản Lý SX | Sản xuất | Quản lý sản xuất |
| `muahang` | Đỗ Mua Hàng | Mua hàng | Nhân viên mua hàng |

**Thêm 1 tài khoản** cho vai trò duyệt cấp 1 phía đề nghị (role "Tổ trưởng SX" đã có nhưng
chưa có user demo):

| `totruongsx` | Bùi Tổ Trưởng | Sản xuất | Tổ trưởng SX |
|---|---|---|---|

**Kịch bản test đi hết luồng:** `nvsx` tạo đề nghị xuất → `totruongsx` duyệt → `thukho` lập
phiếu xuất, chọn lô, in → `ketoankho` xem giá vốn. Đăng nhập lại `nvsx` để kiểm chứng
**không thấy tồn, không thấy giá**.

## 10. In phiếu

Dự án đang có 2 khuôn in, mỗi cái một mục đích:

| Khuôn | File | Dùng khi |
|---|---|---|
| **PrintSheet** — overlay xem trước, logo SVN, header công ty | `frontend/src/components/PrintSheet.tsx` | Chứng từ nội bộ: Lệnh SX, Xác nhận đơn, Phiếu tính giá |
| **printTT200** — pop-up, mẫu Bộ Tài chính, Times New Roman, tiền bằng chữ, ô ký | `frontend/src/utils/printTT200.ts` | Chứng từ kế toán: Phiếu thu (01-TT), Phiếu chi (02-TT) |

Phiếu nhập/xuất kho **có mẫu chính thức trong cùng Thông tư 200/2014/TT-BTC**: **Mẫu 01-VT
(Phiếu nhập kho)** và **Mẫu 02-VT (Phiếu xuất kho)** — kế toán cần đúng mẫu này để đối chiếu.
→ đi theo `printTT200`.

**File mới:** `frontend/src/utils/printStockVoucher.ts`, cùng cấu trúc
`FORM = { nhap: {...}, xuat: {...} }`, dùng lại `amountInWords`, `money`, `dmyParts`,
`escapeHtml` từ `frontend/src/utils/format.ts`.

Bố cục 01-VT / 02-VT:
- Đơn vị · Bộ phận · Số · Ngày · Nợ / Có
- *"Theo … số … ngày … của …"* → **điền số đề nghị** (đúng luật §5: mọi phiếu phải có đề nghị)
- Họ tên người giao/nhận hàng · Nhập/xuất tại kho · địa điểm
- Bảng: `STT | Tên hàng | Mã số | Mã lô | ĐVT | SL theo chứng từ | SL thực nhập/xuất | Đơn giá | Thành tiền`
  - **Mã lô** là cột thêm ngoài mẫu chuẩn — cần cho tính đích danh (§6)
  - **Đơn giá + Thành tiền ẩn khi không có `can_view_cost`**
- Cộng thành tiền **bằng chữ** · Số chứng từ gốc kèm theo
- 5 ô ký: Người lập phiếu · Người giao hàng · Thủ kho · Kế toán trưởng · Giám đốc

**Giấy đề nghị lĩnh vật tư / đề nghị nhập** không có mẫu BTC bắt buộc → in bằng `PrintSheet`.

Số phiếu dùng lại cơ chế `document_sequence` sẵn có.

## 11. Bảng dữ liệu

| Bảng | Cột chính |
|---|---|
| `stock_request` | mã, loại (`NHAP`/`XUAT`), người tạo, bộ phận, ngày cần, mức ưu tiên, **ghi chú**, trạng thái, người duyệt, thời điểm duyệt, lý do từ chối |
| `stock_request_line` | request_id, material_id, đvt, sl_de_nghi, sl_duyet, sl_da_ung, ghi chú dòng |
| `stock_voucher` | mã, loại (`NHAP`/`XUAT`), request_id **(bắt buộc)**, kho, ngày, người lập, người giao/nhận, **ghi chú**, trạng thái |
| `stock_voucher_line` | voucher_id, request_line_id, material_id, lot_id, số lượng, đơn giá *(chỉ phiếu nhập)* |
| `stock_lot` | mã lô, material_id, voucher_id, ngày nhập, ncc, **đơn giá nhập**, sl_ban_dau, sl_con_lai, kho, vị trí, hsd, trạng thái |
| `stock_threshold` | material_id, kho_id, ngưỡng tồn, ngưỡng cận tồn, ngưỡng tối đa, bật cảnh báo |

⚠️ Thêm bảng/cột phải viết vào `backend/app/db_migrations.py` **và** cập nhật
`docs/DB_SCHEMA.md` cùng lúc — `create_all` chỉ TẠO bảng, không ALTER, và DB_SCHEMA.md có
guard test làm `init.ps1` fail nếu thiếu.

## 12. Kiến trúc

Bám phân tầng sẵn có `routers → services → repositories → DB`:

| Tầng | File dự kiến |
|---|---|
| Models | `backend/app/models/stock_request.py`, `stock_voucher.py`, `stock_lot.py` |
| Repositories | `backend/app/repositories/stock_request_repo.py`, `stock_voucher_repo.py`, `stock_lot_repo.py` |
| Services | `backend/app/services/stock_request_service.py` (vòng đời + duyệt), `stock_lot_service.py` (phân bổ lô + giá vốn) |
| Routers | `backend/app/routers/kho_request.py`, `kho_voucher.py` |
| Frontend | `pages/KhoDeNghiPage.tsx`, `pages/KhoYeuCauPage.tsx`, `utils/printStockVoucher.ts` |

Logic nghiệp vụ (chặn ứng vượt duyệt, phân bổ lô, tính giá vốn, so ngưỡng) nằm ở **services**;
router chỉ điều phối; truy vấn DB chỉ trong repositories.

Tái sử dụng component FE sẵn có: `Select` (portal), `ConfirmDialog`, `DiscardChangesDialog`,
`InfoHint`, `useCan` — không tự dựng lại.

Đẩy realtime qua SSE in-process sẵn có (`backend/app/realtime.py`).