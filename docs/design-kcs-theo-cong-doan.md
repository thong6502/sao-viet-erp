# Thiết kế — KCS theo CÔNG ĐOẠN (Giai đoạn → Công đoạn → Checklist)

Trạng thái: **ĐÃ CODE** (08/09/2026) — mục 6 làm hết bước 1→5; còn bước 6 (đối chiếu danh mục
công đoạn) và bước 7 (xác minh dev-browser). Chốt thiết kế cùng ngày với chủ chốt.
Thay thế cách hiểu cũ "KCS = một checklist ở bước cuối routing".

Nguồn nghiệp vụ: tờ **QUY TRÌNH KIỂM SOÁT ISO 9001-2015** đang dùng ở xưởng (ảnh chủ chốt gửi).

---

## 1. Chốt phạm vi

**Làm:**

- KCS tổ chức theo ba tầng **Giai đoạn → Công đoạn → Checklist của công đoạn đó**.
- Giai đoạn lấy thẳng ô **"Giai đoạn"** đang có trên danh mục Công đoạn (`cong_doan.nhom`:
  `prepress` Trước In · `print` In · `finishing` Gia công sau in · `other` Dịch vụ khác).
  KHÔNG đẻ trường mới, KHÔNG đẻ danh mục "giai đoạn KCS" thứ hai.
- Mọi công đoạn có tiêu chí gắn vào đều thành **điểm kiểm**, không riêng bước cuối.

**KHÔNG làm (chủ chốt chốt bỏ):**

- Phần **"QA: KIỂM TRA TRƯỚC IN"** của tờ ISO (số lệnh sản xuất, nguyên liệu giấy, nhà cung cấp
  giấy, giấy giao/cắt cuộn, màng matelize). Đây là **kiểm NGOÀI hệ thống** — không đưa vào phần
  mềm. Ghi lại ở đây để lần sau đừng ai "phát hiện thiếu" rồi dựng lại.
- Dòng **"KẾT THÚC NGÀY"** ở cuối tờ ISO: kiểm theo NGÀY chứ không theo công đoạn của một lệnh,
  cùng loại "ngoài luồng" với trên. Chưa làm.
- Khối **"Tiêu chí KCS bổ sung"** trên drawer bước của Lệnh sản xuất — **gỡ bỏ** (mục 6).

## 2. Đọc đúng tờ ISO

Cột đầu của cả ba khối trong tờ ISO ghi **"TÊN CÔNG ĐOẠN"**, không phải tên tiêu chí. Tức là tờ
giấy hiện tại chỉ liệt kê **công đoạn nào phải kiểm**, rồi ghi tay `GHI CHÚ` / `TÊN THỢ LÀM · NHÓM
LÀM` / `SỐ LƯỢNG ĐẠT` / `SỐ LƯỢNG LỖI` cho công đoạn đó.

Cái phần mềm thêm vào so với tờ giấy là **tầng checklist bên dưới mỗi công đoạn** — kiểm cái gì,
kiểm thế nào, mục nào bắt buộc phải đạt. Đó là lý do vẫn cần danh mục Tiêu chí KCS.

Hệ quả cho seed: **không seed được "26 tiêu chí" từ tờ ISO** (nó không có tiêu chí nào). Việc phải
làm là đối chiếu danh mục Công đoạn đã có đủ mấy cái tên trong tờ ISO chưa (khâu in: máy in số, phủ
vecni, phủ UV, đổi máy in — sau in: kiểm phẩm tờ in, cán màng, phủ UV gốc nước/dầu, phủ keo PET,
bồi sóng carton, bồi giấy với giấy, bế cấn, cắt tề, cắt demi, gỡ phôi, dán máy, dán thủ công, kiểm
phẩm thủ công, đóng gói, giao hàng), còn tiêu chí thì tổ KCS tự khai dần vào danh mục.

## 3. Mô hình dữ liệu — KHÔNG thêm bảng nào

Ba thứ đã có sẵn, chỉ dùng lại:

| Thứ | Bảng / cột đang có | Vai trò trong thiết kế này |
|---|---|---|
| Giai đoạn | `cong_doan.nhom`, đã chụp sang `san_xuat_cong_viec.nhom_cong_doan` | Tầng gom nhóm ngoài cùng — có sẵn trên thẻ việc, không cần join |
| Tiêu chí ↔ công đoạn | `san_xuat_kcs_tieu_chi` + `san_xuat_kcs_tieu_chi_cong_doan` | Kho tiêu chí, nhiều-nhiều với công đoạn |
| Checklist đã chụp | `san_xuat_cong_viec.kcs_tieu_chi_json` | Ảnh chụp lúc phát hành, đóng băng cho lệnh đó |
| Kết quả kiểm | `san_xuat_kcs_batch` (+ `_loi`, `_loi_anh`) | Số nhận / đạt / không đạt, lỗi, ảnh, quy trách nhiệm |

**Đổi duy nhất ở tầng snapshot** (`services/san_xuat/snapshot.py::_checklist`):

- Hiện: chỉ chụp checklist khi `la_kcs=True` (bước cuối + tổ có `is_kcs`), ngoài ra trả `None`.
- Sau: chụp cho **mọi bước có tiêu chí gắn vào công đoạn của nó**. Không có tiêu chí nào ⇒ vẫn
  `None` (đừng ghi `[]` — cột NULL chính là bộ lọc "việc này có phải điểm kiểm không" ở mục 4).
- Bỏ vòng lặp đọc `kcs_tieu_chi_bo_sung_json` và bỏ khoá `nguon` (chỉ còn một nguồn là danh mục).

**`la_kcs` giữ NGUYÊN nghĩa cũ** — "thẻ việc này thuộc về tổ KCS" (bước KCS thành phẩm đứng trong
routing). Đừng bật `la_kcs` cho mọi công đoạn có checklist: làm thế là ném toàn bộ việc sản xuất
lên bàn KCS và phá luôn `la_kcs_cuoi` (cửa nhập kho thành phẩm). Hai khái niệm tách rời:

- `la_kcs` = **ai sở hữu thẻ việc**.
- `kcs_tieu_chi_json IS NOT NULL` = **thẻ việc này là một điểm kiểm**.

**`san_xuat_kcs_batch.loai`** có **BA** giá trị (đổi so với bản chốt đầu, xem mục 7):

- `routing` — bước `la_kcs` trong routing của chính tổ KCS. Đây là loại DUY NHẤT đẻ thêm một dòng
  năng suất `san_xuat_batch` và mở cửa "Tạo yêu cầu nhập kho".
- `dot_xuat` — kiểm ngoài kế hoạch, không có checklist.
- `diem_kiem` — **mới**: tổ KCS đi kiểm một công đoạn giữa chuỗi của tổ KHÁC, có checklist.

`diem_kiem` dùng lại nguyên thân của `dot_xuat`: **không** đẻ `san_xuat_batch`, **không** đụng
`trang_thai` thẻ việc, **không** đụng kho. Chính vì vậy "không đạt" ở điểm kiểm **không chặn bước
sau** — đó là hệ quả của cấu trúc chứ không phải một luật chính sách phải nhớ đi nhớ lại.

**Bẫy `JSON(none_as_null=True)`** (mất nửa buổi vì nó, ghi ra đây): kiểu `JSON` của SQLAlchemy mặc
định ghi Python `None` thành chuỗi JSON `'null'` chứ KHÔNG phải NULL của SQL, nên bộ lọc "có
checklist" (`kcs_tieu_chi_json IS NOT NULL`) khớp CẢ dòng không có checklist. Cột đã khai lại
`JSON(none_as_null=True)`; migration **`0284_kcs_tieu_chi_json_null_that`** nắn dòng cũ
(`CAST(... AS TEXT) = 'null'` → NULL). Kiểu cột không đổi nên `docs/DB_SCHEMA.md` giữ nguyên.

**Thợ / nhóm làm** (cột `TÊN THỢ LÀM · NHÓM LÀM` của tờ ISO): **đọc từ thẻ việc**, không chép sang
bảng KCS. Thẻ việc đã biết tổ, người được phân công và máy. Chép lần hai là đẻ hai nguồn sự thật.

## 4. Màn KCS đổi bố cục

`ThucHienKcsPage` giữ khối "Chờ KCS" cũ (`workItems(teamId, "kcs")`) và **thêm** một khối thứ hai
"Điểm kiểm theo công đoạn" đọc từ endpoint mới:

- `GET /api/san-xuat/kcs/diem-kiem` → `{giai_doan: [{nhom, cong_viec[]}]}`. **Không nhận `team_id`**:
  tổ KCS đi kiểm việc của tổ KHÁC nên phạm vi là `_to_thay_duoc` (mọi tổ người xem được đọc), giống
  cách bộ chọn việc của "Kiểm đột xuất" vẫn làm. Điều kiện dòng: đã phát hành, `kcs_tieu_chi_json
  IS NOT NULL`, và **đã khởi động** (`running|paused|completed`) — khớp đúng cổng ghi
  `_TRANG_THAI_GHI_DUOC`, để không bày dòng nào bấm vào là 400.
- Payload đã gộp sẵn `checklist[]` + `batch[]` + `tong_dat`/`tong_loi` + `nguoi[]` (tên thợ đang
  được phân công — cột "TÊN THỢ LÀM" của tờ ISO), nên FE **không** phải fan-out `kcsChiTiet` từng
  việc như khối "Chờ KCS".
- FE bỏ khỏi khối này thẻ việc của **chính tổ KCS đang mở trang** — chúng đã nằm ở "Chờ KCS" cùng
  cửa nhập kho; bày hai lần là hai chỗ ghi cho một việc.
- Ghi kết quả: `POST /api/san-xuat/kcs/kiem` với `loai=diem_kiem` (**đổi tên** từ
  `POST /kcs/dot-xuat`; cùng handler phục vụ cả `dot_xuat` lẫn `diem_kiem`, `loai` là trường bắt
  buộc — dự án chưa có user thật nên không giữ đường cũ).

Ba tầng bày như sau:

```
GIAI ĐOẠN: In                                    (nhom_cong_doan = "print")
  └─ Công đoạn: In offset 4 màu · LSX26-0018 · Tổ in · Máy in-11
       ├─ ☐ Chồng màu đúng                      *bắt buộc
       ├─ ☐ Không lem mực ở biên
       └─ ☐ Đúng mẫu đã ký                      *bắt buộc
       Số đạt ____   Số lỗi ____        Thợ: (đọc từ thẻ việc)
GIAI ĐOẠN: Gia công sau in
  └─ Công đoạn: Bế · ...
```

- Thứ tự giai đoạn cố định `prepress → print → finishing → other`; trong một giai đoạn xếp theo
  thứ tự bước của routing.
- Nhóm rỗng thì **ẩn hẳn**, không bày tiêu đề giai đoạn trống.
- `KcsResultDrawer` giữ nguyên bốn khối (ngữ cảnh · checklist · đạt/lỗi · lỗi+ảnh). Chỉ đổi nguồn
  của khối 1: nay là "công đoạn bất kỳ", không mặc định là bước cuối. Nút "Tạo yêu cầu nhập kho"
  vẫn chỉ hiện ở thẻ `la_kcs_cuoi` — không đổi.
- `_validate_checklist_bat_buoc` (services/san_xuat/kcs.py) giữ nguyên: tiêu chí `bat_buoc` chưa
  trả lời thì không cho gửi kết luận. Nay nó áp cho mọi điểm kiểm, không riêng bước cuối.

## 5. Màn khai báo — CÂY Giai đoạn → Công đoạn → hạng mục (chốt 08/09/2026)

Chủ chốt chốt luồng nhập liệu: *"khi tạo mới là chọn giai đoạn, chọn giai đoạn xong sẽ nhập công
đoạn (tự select và thêm theo công đoạn), với mỗi công đoạn thì sẽ thêm hạng mục kiểm tra cho công
đoạn — HẾT"*. Bản đầu làm ngược (một tiêu chí rồi tick nhiều công đoạn) — đã sửa.

**Mô hình đổi theo**: `san_xuat_kcs_tieu_chi` nay THUỘC ĐÚNG MỘT công đoạn (`cong_doan_id` FK),
bảng nối nhiều-nhiều `san_xuat_kcs_tieu_chi_cong_doan` **gỡ hẳn** ở mg `0285` (dòng cũ gắn n công
đoạn được tách thành n dòng, mã thêm hậu tố `-2`, `-3`…). Cùng câu chữ dùng cho hai công đoạn thì
khai hai dòng — đúng như tờ ISO, mỗi khối liệt kê gạch đầu dòng của riêng nó.
`UniqueConstraint(cong_doan_id, ten)` chặn khai trùng trong CÙNG công đoạn.

**GIAI ĐOẠN không phải bản ghi**: nó là `cong_doan.nhom` sẵn có, chỉ dùng để gom nhóm khi đọc và
lọc ô chọn khi thêm. Không đẻ bảng "giai đoạn KCS".

**Màn**: `frontend/src/pages/danh-muc/KcsKhaiBaoPage.tsx` — màn RIÊNG, không dùng nền
`RebuildCatalogPage` (nền đó bày bảng phẳng, mỗi dòng một bản ghi; ở đây đơn vị người dùng nghĩ
tới là công đoạn với các gạch đầu dòng bên dưới). Khối trên cùng "Thêm công đoạn cần kiểm": chọn
giai đoạn → ô công đoạn lọc theo giai đoạn đó và **bỏ** công đoạn đã có trong cây → bấm thêm
hạng mục đầu tiên. Mỗi thẻ công đoạn có nút "+ Hạng mục" riêng, form mở NỘI TUYẾN dưới bảng để
người khai nhìn thấy các mục đã có mà không viết lại cùng một ý.

**API**: `GET /api/san-xuat-kcs-tieu-chi/khai-bao` trả sẵn ba tầng (đăng ký TRƯỚC
`make_catalog_router`, nếu không `GET /{item_id}` nuốt mất đường này). Ghi vẫn đi CRUD nền
(`POST ""` · `PUT /{id}` · `DELETE /{id}`); `ma` sinh ngầm `KM####`, UI không có ô nhập mã.

## 6. Gỡ "Tiêu chí KCS bổ sung"

Từ nay tiêu chí có **một nguồn duy nhất** là danh mục. Muốn thêm cho một công đoạn thì khai vào
danh mục và nó áp cho mọi lệnh chạy công đoạn đó.

Gỡ trọn, không để cột lơ lửng (dự án chưa có dữ liệu thật — xem memory `du-an-dang-dev-chua-co-user`):

- Migration mới: `DROP COLUMN kcs_tieu_chi_bo_sung_json` ở `lsx_cong_doan` **và**
  `bai_ghep_cong_doan`. Cập nhật `docs/DB_SCHEMA.md` **cùng lúc** (guard test sẽ đỏ nếu quên).
- `LsxBuocDrawer.tsx`: xoá cả `<section>` "Tiêu chí KCS bổ sung".
- `lsxBuoc.ts`: xoá khỏi `EditRow`, khỏi payload, khỏi `mac_dinh_buoc`.
- `schemas/lsx.py`, `api/client.ts`, `lsx_service.py`: xoá field khỏi in/out.
- `snapshot.py::_checklist`: xoá vòng lặp `bo_sung_lsx` (mục 3).

Còn `la_kcs` trên drawer bước thì **giữ** — nó vẫn quyết bước nào thuộc tổ KCS.

## 7. Thứ tự làm

0. Màn khai báo theo cây + mg `0285` (mục 5) — **xong 08/09/2026**, đã thao tác lại bằng UI thật.
1. Migration DROP hai cột + cập nhật `docs/DB_SCHEMA.md`.
2. `snapshot._checklist`: bỏ gate `la_kcs`, bỏ nguồn bổ sung, giữ NULL khi rỗng. Test snapshot.
3. Backend: repo/endpoint lấy điểm kiểm theo `kcs_tieu_chi_json IS NOT NULL` + trả kèm
   `nhom_cong_doan`, thứ tự bước, tổ/người/máy. Test service.
4. Frontend: `ThucHienKcsPage` đổi sang ba tầng; `KcsResultDrawer` nới ngữ cảnh.
5. Gỡ khối "Tiêu chí KCS bổ sung" khắp FE/BE (mục 6).
6. Đối chiếu danh mục Công đoạn với danh sách trong tờ ISO, bổ sung cái còn thiếu.
7. Xác minh bằng dev-browser đúng luồng: khai tiêu chí ở danh mục → phát hành lệnh → mở bàn KCS
   thấy đủ ba tầng → ghi đạt/lỗi ở một công đoạn giữa chuỗi (không phải bước cuối) → kiểm tiêu chí
   bắt buộc có chặn không.

## 8. Hai điểm treo — ĐÃ CHỐT 08/09/2026

- **Ai ghi kết quả ở công đoạn giữa chuỗi: TỔ KCS ĐI KIỂM.** Không phải tổ đang chạy tự khai rồi
  KCS duyệt. Vì thế `kcs_department_id` của batch là tổ KCS, còn `cong_viec_id` trỏ sang thẻ việc
  của tổ khác — đúng hình dạng mà `dot_xuat` vốn đã dùng, không cần cột mới.
- **Kiểm "không đạt" KHÔNG chặn bước sau** — chỉ ghi nhận chất lượng. Hiện thực bằng cấu trúc:
  `loai=diem_kiem` không đẻ `san_xuat_batch`, không đổi `trang_thai`, không đụng kho (mục 3).
