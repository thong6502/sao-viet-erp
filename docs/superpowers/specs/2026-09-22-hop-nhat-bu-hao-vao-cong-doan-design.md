# Thiết kế hợp nhất Bù hao vào Công đoạn

Ngày: 22/09/2026  
Trạng thái: Đã duyệt thiết kế

## 1. Mục tiêu

Bỏ module/danh mục Bù hao độc lập và đưa toàn bộ cấu hình bù hao vào từng Công đoạn.

Không tạo màn hình hoặc luồng mới. Người dùng khai bù hao ngay trong drawer tạo/sửa Công đoạn.

## 2. Phạm vi

- Gỡ mục Bù hao khỏi sidebar.
- Gỡ trang, API, registry và quyền riêng `dm_bu_hao`.
- Công đoạn tự sở hữu cấu hình bù hao.
- Giữ nguyên chức năng tính bù hao trong tính giá, bài ghép và lệnh sản xuất.
- Chuyển dữ liệu bù hao hiện tại sang từng Công đoạn.
- Cập nhật import/export Công đoạn.

Không xóa vật lý bảng và cột cũ trên DB live.

## 3. Giao diện Công đoạn

Khối Bù hao nằm sau khối Đơn vị trong luồng chỉnh sửa Công đoạn hiện tại.

Trường `Cách tính bù hao` có ba chế độ:

### 3.1. Không bù hao

Không hiện thêm trường. Giá trị bù hao bằng 0.

### 3.2. Điền tổng cố định

Hiện ô `Số tờ bù hao`.

Giá trị được cộng trực tiếp vào số lượng đầu vào của công đoạn.

### 3.3. Theo bậc số lượng

Hiện bảng gồm:

- Khoảng số lượng
- Giá trị
- Đơn vị: `Tờ` hoặc `%`
- Thao tác xóa

Người dùng chỉ nhập mốc trên. Hệ thống tự nối các khoảng:

- Bậc đầu: `Đến X`
- Bậc giữa: `Trên X đến Y`
- Bậc cuối: `Trên Y`

Bậc cuối luôn là vô hạn. Nút `Thêm bậc` chèn một bậc trước bậc vô hạn.

Không cho nhập trực tiếp `Từ SL`, nhằm loại bỏ khoảng trùng và khoảng hở.

Danh sách Công đoạn hiển thị:

- `Không bù hao`
- `Cố định N tờ`
- `Theo N bậc`

## 4. Mô hình dữ liệu

Công đoạn sử dụng:

- `kieu_bu_hao`: `khong | co_dinh | theo_bac`
- `so_to_bu_hao`: số tờ khi dùng chế độ cố định
- `bac_bu_hao`: JSON chứa danh sách bậc

Cấu trúc một bậc:

```json
{
  "sl_den": 3000,
  "gia_tri": 150,
  "don_vi": "to"
}
```

Bậc cuối có `sl_den = null`.

`bu_hao_id` không còn nằm trong model, schema hoặc API mới.

## 5. Quy tắc tính toán

- Đơn vị `Tờ`: cộng trực tiếp số tờ.
- Đơn vị `%`: nhân tỷ lệ với sản lượng cần ra của chính công đoạn.
- Ranh giới bậc dùng quy tắc:
  - Bậc đầu: `0 < SL <= mốc đầu`
  - Bậc giữa: `mốc trước < SL <= mốc hiện tại`
  - Bậc cuối: `SL > mốc cuối`
- Khi tính ngược chuỗi sản xuất, mỗi công đoạn tra bậc bằng sản lượng của chính bước đó.
- Không dùng một sản lượng chung để tra toàn chuỗi.

## 6. Validation

Backend và frontend cùng kiểm tra:

- Chế độ `theo_bac` phải có ít nhất một bậc.
- Các mốc hữu hạn phải tăng dần.
- Chỉ có một bậc vô hạn và phải nằm cuối.
- Giá trị không được âm.
- Đơn vị chỉ nhận `to` hoặc `pct`.
- Chế độ cố định phải có số tờ không âm.

Giao diện báo lỗi tại dòng sai và không đóng drawer khi lưu lỗi.

## 7. Migration

Migration mới trong `backend/app/db_migrations.py`:

1. Thêm `bac_bu_hao` vào bảng `cong_doan`.
2. Với Công đoạn đang `kieu_bu_hao = tra_bang`:
   - Đọc `bu_hao_id`.
   - Sao chép `bu_hao.bac` vào `cong_doan.bac_bu_hao`.
   - Đổi chế độ thành `theo_bac`.
3. Công đoạn dùng chung mã cũ nhận các bản sao độc lập.
4. Nếu mã nguồn không còn tồn tại:
   - Giữ chế độ `theo_bac`.
   - Lưu danh sách rỗng.
   - Giao diện hiển thị `Chưa khai bậc bù hao`.

Bảng `bu_hao` và cột `bu_hao_id` cũ không bị DROP trên DB live. Chúng trở thành dữ liệu mồ côi để đối chiếu, nhưng code mới không đọc hoặc ghi.

## 8. Gỡ module độc lập

Gỡ khỏi luồng ứng dụng:

- Mục Bù hao trong sidebar.
- Catalog config Bù hao.
- Catalog registry Bù hao.
- Router/API Bù hao.
- Quyền `dm_bu_hao` trong ma trận phân quyền.
- Import/export riêng của Bù hao.
- Các tham chiếu chọn mã Bù hao trong Công đoạn.

Việc gỡ không ảnh hưởng các khái niệm bù hao khác trong tính giá, vật tư hoặc sản xuất.

## 9. Import/export Công đoạn

File Công đoạn mang theo:

- Kiểu bù hao
- Số tờ cố định
- Các bậc số lượng, giá trị và đơn vị

Không yêu cầu import danh mục Bù hao trước Công đoạn.

## 10. Chốt chi tiết triển khai

### 10.1. Mã nguồn module cũ

Gỡ khỏi mã nguồn: `models/bu_hao.py`, `schemas/bu_hao.py`, `repositories/bu_hao_repo.py`,
`services/bu_hao_service.py`, `routers/bu_hao.py`, dòng `DanhMuc("bu_hao", …)` trong
`catalog_registry.py`, `_bu_hao` trong `danh_muc_tham_chieu.py`, config Bù hao trong
`rebuildCatalogConfigs.tsx`, mục sidebar, và quyền `dm_bu_hao` (khai ở CẢ `seed.py` lẫn
`PermissionMatrix.tsx`).

Model bị gỡ nên `docs/DB_SCHEMA.md` phải XÓA mục bảng `bu_hao` và cột `cong_doan.bu_hao_id`,
đồng thời THÊM `cong_doan.bac_bu_hao`. Guard test chấm theo model — thiếu một vế là `init` đỏ.

Không viết lệnh DROP. Bảng `bu_hao` và cột `bu_hao_id` trên DB đang chạy thành dữ liệu mồ côi
đúng như §7.

### 10.2. Giá trị lưu của `kieu_bu_hao`

Lưu `theo_bac` như §4. Migration đổi bằng raw SQL đích danh cột, không ORM full-select:

```sql
UPDATE cong_doan SET kieu_bu_hao = 'theo_bac' WHERE kieu_bu_hao = 'tra_bang'
```

Sửa kèm: hằng `KIEU_BU_HAO` trong model, `seed_rebuild.py`, `import_danh_muc_prod.py`,
`catalog_excel_specs.py`, nhãn trong `nhat_ky_danh_muc.py`, và hằng `KIEU_BU_HAO` phía frontend.

### 10.3. Bậc bù hao trong Excel

Cột "Mã bù hao" (`bu_hao_id`) trong spec Công đoạn bị gỡ. Bậc đi thành SHEET CON "Bậc bù hao"
(`SheetCon(field="bac_bu_hao")`), ba cột `Đến SL` / `Giá trị` / `Đơn vị` — không nhồi một ô
chuỗi kiểu `3000:150:to | *:2:pct` như bản nháp trước.

Lý do đổi: spec CONG_DOAN đã sẵn hai sheet con cùng dạng ("Bậc đơn giá", "Bậc theo khổ") nên đây
là đường mòn có sẵn, và chính spec BU_HAO cũ cũng ghi chú rằng nhồi JSON vào một ô thì người khai
không sửa nổi trong Excel. Hàng để trống `Đến SL` là bậc vô hạn. Đọc vào áp đúng bộ kiểm tra ở §6.

### 10.4. Nhật ký danh mục

`bac_bu_hao` không in JSON thô. Nhật ký diễn thành câu, mỗi bậc một dòng:
`Đến 3.000 → 150 tờ`, `Trên 3.000 đến 10.000 → 3%`, `Trên 10.000 → 2%`.
Nhãn cột là "Bậc bù hao"; nhãn "Mã bù hao" (`bu_hao_id`) bị gỡ.

### 10.5. Ba điểm đã kiểm trong mã nguồn hiện tại

- `bu_hao_engine.tra_bac_raw` đang lấy cận dưới từ `b["sl_tu"]`. Bậc mới không còn ô ấy nên cận
  dưới phải suy từ mốc của bậc LIỀN TRƯỚC — đây là thay đổi BẮT BUỘC về nguồn dữ liệu, không phải
  chuyện tối ưu. (Với danh sách đã sắp tăng dần và lấy bậc khớp đầu tiên thì để cận dưới bằng 0
  cho kết quả y hệt; nên đừng nói cách kia "sai im lặng" — không dựng được ca chứng minh.)
- Nhánh dò `CongDoan.bu_hao_id` trong `tinh_gia_service` (cảnh báo "danh mục đã đổi", lỗi 8
  ngày 25/08/2026) gỡ theo. Bậc nằm trên chính công đoạn, mà công đoạn đã có trong danh sách
  đối chiếu — đây là gỡ code thừa, không phải mất cảnh báo.
- Ô `bands` (`fields/Bands.tsx`) đang phục vụ danh mục Bù hao được tái dùng cho `bac_bu_hao`:
  bỏ ô "Từ SL", cột đầu đổi thành nhãn khoảng chỉ để đọc, hàng vô hạn khóa ở cuối ngay khi mở.
