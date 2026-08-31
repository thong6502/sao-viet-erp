# Xuất/Nhập Excel danh mục — thiết kế

Trạng thái: ĐÃ LÀM cho **đủ 13 màn** Cấu hình danh mục (29/08/2026). Nguồn hiện hành là
[`services/catalog_excel_specs.py`](../backend/app/services/catalog_excel_specs.py) — mỗi màn một
`CatalogExcelSpec`; tài liệu này giải thích LUẬT và lý do, không chép lại danh sách cột.

## Vì sao có tài liệu này

Đợt trước (5 màn) nhét cơ chế Excel thẳng vào `catalog_base.make_catalog_router` dưới dạng bốn
tham số (`enable_import`, `import_columns`, `import_resolve`, `export_resolve`) và chỉ tả được MỘT
sheet phẳng. Hệ quả: 8 màn không bật được, và ngay ở 5 màn bật được thì mọi cấu hình dạng BẢNG CON
(bậc bù hao, đầu việc định mức, gói bảo trì, cặp quy đổi) hoặc rơi mất, hoặc bị nén thành một ô
JSON thô không sửa nổi bằng tay.

Nay router chỉ nhận MỘT tham số `excel_spec`; toàn bộ cơ chế nằm ở
[`services/catalog_excel.py`](../backend/app/services/catalog_excel.py), toàn bộ khai báo nằm ở
`catalog_excel_specs.py`.

## Phạm vi

- Hai nút `Xuất Excel` / `Nhập Excel` nằm NGAY trên từng màn trong 13 màn Cấu hình danh mục. Không
  có màn riêng, không có luồng riêng.
- Xuất CHỈ bản ghi `active=true`, nhưng phải chứa TOÀN BỘ cấu hình hiện hành — đặc biệt mọi công
  thức, bậc tính và dữ liệu con ảnh hưởng nghiệp vụ.
- KHÔNG xuất/nhập lịch sử: nhật ký sửa đổi, phiên bản giá giấy, lịch sử công thức, giá trị "lần
  trước" và thời điểm sửa. Cũng loại id nội bộ, mốc thời gian hệ thống, dữ liệu dẫn xuất, ảnh và
  trạng thái vận hành hiện thời.

## Hợp đồng workbook

| Màn | Các sheet con ngoài sheet chính |
|---|---|
| Loại sản phẩm | Chuỗi công đoạn mặc định (có thứ tự, theo mã Công đoạn) |
| Máy | Nhóm máy · Khoản chuẩn bị · Gói bảo trì · Hạng mục bảo trì |
| Công đoạn | Nhóm máy cho phép · Bậc đơn giá · Bậc theo khổ · Đầu việc định mức · Vật tư đầu việc |
| Bù hao | Bậc bù hao |
| Đơn vị & quy đổi | Các cặp quy đổi |
| Giấy | Giấy thay thế |
| Vật tư khác | Vật tư thay thế |
| 6 màn còn lại | Một sheet chính chứa toàn bộ trường cấu hình hiện hành |

Luật chung:

1. Sheet chính luôn có `Mã`, các trường cấu hình/công thức và `Trạng thái`. File xuất có **CẢ dòng
   đã ngừng dùng** (`Trạng thái=FALSE`) — vì một dòng đang dùng ở màn này hoàn toàn có thể trỏ tới
   một dòng đã ngừng ở màn kia, lọc đi thì bộ file xuất ra không tự nhập lại được sang máy khác.
   Đổi ô `Trạng thái` rồi nhập là ngừng/bật lại được cả hai chiều.
2. FK và danh sách liên kết dùng **mã nghiệp vụ**; phòng ban và khách hàng dùng mã hệ thống kèm
   cột TÊN đối chiếu (`chi_doc` — không bao giờ được GHI, nhưng khi nhập thì ĐƯỢC ĐỌC để kiểm
   chéo: tên trong file mà khác tên của bản ghi mà cột mã đang trỏ tới thì báo lỗi, không ghi).
   Mã do máy cấp theo thứ tự tạo (`PB008`, `KH003`…) nên hai máy rất dễ lệch nhau — không kiểm chéo
   thì dữ liệu lặng lẽ rơi vào nhầm phòng ban/khách hàng. Không bao giờ dùng id số.
3. Collection có cột `Thứ tự`. Mã gói bảo trì của Máy được GIỮ NGUYÊN vì đang là neo của phiếu bảo
   trì (`ky_thuat_bao_tri.goi_id`).
4. Các khoá chưa biết trong `fields_theo_loai` của Máy nằm ở sheet ẩn `_giu_nguyen` để round-trip;
   các cấu hình đã biết được trình bày bằng sheet dễ đọc, không bắt ai sửa JSON.
5. Sheet ẩn `_meta` chứa loại danh mục + phiên bản định dạng. File đời cũ (không `_meta`) của 5 màn
   đang hỗ trợ vẫn nhận theo chế độ tương thích. Thiếu sheet con ⇒ GIỮ NGUYÊN dữ liệu con.
6. Bản ghi không xuất hiện trong sheet chính thì giữ nguyên (không xoá). Với mã cha CÓ trong sheet
   chính, sheet con hiện diện thay TRỌN tập con — xoá dòng con khỏi file nghĩa là xoá cấu hình con
   đó.
7. Ô trống ở một cột CÓ MẶT sẽ xoá giá trị; thiếu hẳn cột thì giữ giá trị cũ.

## Cơ chế

- `CatalogExcelSpec` khai sheet, cột, kiểu, khoá, resolver và tập loại trừ (`loai_tru`).
- Engine `xuat_excel` / `nhap_excel`: dựng workbook, đọc file, chuẩn hoá mã, kiểm công thức/tham
  chiếu, dựng KẾ HOẠCH thay đổi rồi chạy.
- Sheet loại `ap_dung` (cặp quy đổi của Đơn vị — ghi ra bảng nằm NGOÀI model chính) chạy ở **LƯỢT
  HAI**, sau khi mọi dòng chính đã ghi xong. Nó tra mã ngay trong chính danh mục này, nên `ram → to`
  mà `to` nằm dưới `ram` trong file thì tra lúc ghi dòng `ram` là chưa có. Sắp thứ tự lúc xuất
  không cứu được (người dùng chèn dòng mới vào cuối file), và cả file là MỘT giao dịch nên nhập
  hai lượt cũng không xong.
- Resolver FK báo lỗi kèm TÊN MÀN phải khai trước (`Khai xong màn "Chủng loại giấy" rồi nhập lại
  màn này.`) — chặn theo phụ thuộc là đúng thiết kế, việc của thông báo là chỉ đúng chỗ cần đi.
- **Guard test** đối chiếu mọi field repository cho phép ghi với field Excel hoặc `loai_tru`. Thêm
  một công thức mới mà quên Excel là test đỏ ngay
  (`test_guard_moi_truong_ghi_duoc_deu_di_qua_excel_hoac_duoc_loai_tru`).

Endpoint giữ nguyên:

- `GET {prefix}/mau-excel` — xuất toàn bộ bản ghi, cả đang dùng lẫn đã ngừng (danh mục rỗng ⇒ chỉ dòng tiêu đề, tự
  đóng vai file mẫu; vì thế KHÔNG còn nút "Tải mẫu" riêng).
- `POST {prefix}/import-excel?mode=preview|commit` — CÙNG một response
  (`hop_le`, `tong_dong`, `tao_moi`, `cap_nhat`, `khong_doi`, `da_ghi`, và lỗi
  `{sheet, dong, cot, ly_do}`). File không đọc được hoặc sai loại màn ⇒ `422`. Lỗi dữ liệu ⇒
  preview `hop_le=false`, không ghi gì.

`preview` và `commit` dùng CHUNG parser/executor — con số xem trước là con số thật, kể cả lỗi chỉ
lộ ra lúc service validate. Commit kiểm lại rồi chạy trong MỘT unit-of-work: service/repository chỉ
`flush`, audit và dữ liệu cùng giao dịch, commit một lần cuối hoặc rollback toàn bộ.

### Bẫy: SAVEPOINT trên SQLite

`mot_giao_dich` chạy mỗi dòng trong một `begin_nested()`. Driver `sqlite3` chỉ tự phát `BEGIN`
trước INSERT/UPDATE/DELETE, **không** phát trước `SAVEPOINT` — nên savepoint đầu tiên thành savepoint
NGOÀI CÙNG, mà `RELEASE` một savepoint ngoài cùng trong SQLite CHÍNH LÀ commit. Kết quả: `rollback()`
không còn gì để huỷ và luật "cả file là một giao dịch" âm thầm mất hiệu lực — chỉ trên SQLite (bộ
test), Postgres dev/prod không dính. `_ep_mo_giao_dich()` mở sẵn giao dịch thật trước khi vào vòng.

Không vá ở `db._make_engine` (bản vá chính chủ của SQLAlchemy: tắt `isolation_level` + tự phát
`BEGIN` qua event) vì nó vỡ với `StaticPool`: cả app dùng CHUNG một connection nên hai giao dịch
SQLAlchemy song song thành `cannot start a transaction within a transaction`.

## Frontend

- Excel bật cho đủ 13 `REBUILD_CONFIGS` (`enableImport: true`).
- HAI mức quyền: `Xuất Excel` chỉ cần quyền ĐỌC; `Nhập Excel` đòi CẢ `create` LẪN `update` (một
  dòng có thể là tạo mới hoặc cập nhật) — server gác `/import-excel` bằng đúng cặp đó.
- `ImportExcelDialog` là hai bước: chọn file → xem trước → danh sách lỗi hoặc nút `Xác nhận nhập`
  → tải lại bảng.
- Dòng không đổi KHÔNG ghi audit; mọi dòng tạo/cập nhật vẫn ghi nhật ký người nhập.

Không đổi schema DB, không cần migration.

## Kiểm thử

[`backend/tests/test_import_excel.py`](../backend/tests/test_import_excel.py) — nhiều màn được lặp
BÊN TRONG một test vì fixture `client` dựng lại schema mỗi test (~3s/test).

- Đủ 13 màn: đúng sheet/cột, chỉ xuất active, mọi công thức hiện hành có mặt, mọi trường lịch sử bị
  loại, FK ra mã chứ không ra id, bảng con ra sheet đọc được chứ không JSON.
- Round-trip từng màn: xuất → preview → commit mà không sửa file phải cho toàn bộ dòng `khong_doi`
  và KHÔNG đẻ dòng nhật ký nào.
- Sửa công thức, bậc tính, thứ tự, dữ liệu con; xoá dòng con; ô trống; thiếu cột/sheet; tạo mới và
  cập nhật theo mã.
- File sai màn/phiên bản, trùng mã, sai kiểu, công thức không hợp lệ, tham chiếu không tồn tại và
  lỗi ở dòng CUỐI đều rollback toàn bộ.
- Quyền đọc/create/update, và nhập được file Excel định dạng cũ của 5 màn đời trước.

## Phụ lục — quyết định đời trước (giữ để khỏi bàn lại)

1. Gộp "Tải mẫu" + "Xuất Excel" thành MỘT nút: danh mục rỗng thì file xuất tự đóng vai file mẫu.
2. Nhập là UPSERT theo mã, KHÔNG xoá qua Excel — dòng biến mất khỏi file không có nghĩa là xoá.
   Muốn ngừng dùng thì đặt `Trạng thái=FALSE`.
3. Loại trừ cả 3 loại "lịch sử": nhật ký sửa đổi, phiên bản giá giấy (`giay/{id}/versions`), và cột
   "lần trước công thức" (`cong_thuc_*_truoc` / `*_sua_luc`).
4. `fields_theo_loai` của Máy: đợt trước chốt "một cột JSON thô". Đợt này ĐÃ THAY — hai khoá đã
   biết (`chuan_bi_khoan`, `lich_bao_tri` + hạng mục) tách thành ba sheet đọc được, khoá lạ đẩy vào
   sheet ẩn `_giu_nguyen`. Cột "Field theo loại (JSON)" đời cũ vẫn ĐỌC được khi nhập (`chi_nhap`),
   nhưng không còn xuất ra.
