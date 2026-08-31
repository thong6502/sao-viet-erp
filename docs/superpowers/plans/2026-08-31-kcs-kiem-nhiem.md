# Module KCS kiêm nhiệm cho tổ có cờ KCS — Implementation Plan

> **Ghi chú định dạng:** Bản kế hoạch này ở mức thiết kế + trình tự theo Task (business rules, API,
> migration, UI), CHƯA ở dạng bite-sized TDD (Step 1..5 kèm code cụ thể) mà
> `superpowers:writing-plans` yêu cầu cho subagent-driven execution. Trước khi giao từng Task cho
> subagent, cần soạn thêm phần Step/code chi tiết cho Task đó.
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Cho tổ sản xuất có `departments.is_kcs=true` hai cửa làm việc riêng — sản xuất bình thường
và KCS (theo bước routing + kiểm đột xuất) — dùng chung tổ/quyền/dữ liệu/SSE, chỉ ghi kết quả cuối
(Đạt/Lỗi/checklist/bằng chứng), không có giao người/bấm giờ/duyệt/nhận-từ chối trách nhiệm.

**Architecture:** Tách cờ "tổ có năng lực KCS" (`Department.is_kcs`, đã có) khỏi cờ "bước là KCS"
(`CongDoan.la_kcs` → snapshot `LsxCongDoan.la_kcs` → `BaiGhepCongDoan.la_kcs` → phát hành thành
`SanXuatCongViec.la_kcs`, MỚI). Mở rộng `SanXuatKcsBatch`/`SanXuatKcsLoi` hiện có (không dựng hệ
phiếu chất lượng song song), thêm danh mục checklist KCS nhiều-nhiều với Công đoạn, gộp vào màn Cấu
hình danh mục hiện có. Board/API tách theo `mode=production|kcs`; gửi kho là một nút tính tự động
"số đạt chưa gửi", không nhận số từ client.

**Tech Stack:** Backend FastAPI/SQLAlchemy (routers → services → repositories → DB), Postgres
dev/prod, SQLite test; Frontend React/TypeScript; pytest; `./init.ps1` (pytest + compileall) là lệnh
verify chuẩn duy nhất.

**Spec:** Tài liệu này tự thân vừa là spec vừa là trình tự Task (xem toàn văn bên dưới, mục 1–10).
Task 12 (mục 8) sẽ chốt lại nội dung vào `docs/spec-thuc-hien-san-xuat.md` và `docs/DB_SCHEMA.md` sau
khi hoàn tất — hai file đó hiện CHƯA phản ánh module KCS kiêm nhiệm.

## Global Constraints

- KHÔNG có Alembic — mọi cột/bảng mới phải qua `backend/app/db_migrations.py` (idempotent, tự kiểm
  đã có bảng/cột chưa) + cập nhật `docs/DB_SCHEMA.md` cùng lúc (guard test bắt buộc).
- Boolean mới: `server_default` phải là `false`/`true` (Python bool), KHÔNG phải chuỗi `"0"`/`"1"`.
- Không suy `la_kcs` theo tên công đoạn hay theo `department.is_kcs` — chỉ theo cờ bước đã snapshot.
- Không xóa `SanXuatKcsLoi`/kết quả KCS — mọi sửa là điều chỉnh có audit + `expected_version`.
- Không tạo `SanXuatBatch` năng suất hay phân bổ lương khoán từ kết quả KCS.
- Không tự động tạo yêu cầu nhập kho — luôn cần người dùng bấm nút; server tự tính số lượng, không
  nhận số từ client.
- Không có luồng Nhận/Từ chối trách nhiệm, không phân xử tranh chấp trên phần mềm cho phiếu mới; hồ
  sơ `pending/accepted/rejected` cũ chỉ giữ để đọc lịch sử.
- Sửa route/schema backend → phải RESTART uvicorn (không hot-reload đáng tin ở đây).
- Luồng có UI (kể cả chỉ sửa 1 khâu) → BẮT BUỘC thao tác lại bằng chuột/bàn phím thật trên
  dev-browser trước khi báo xong, không dùng API/curl thay bước nào; nếu buộc phải tắt qua API ở một
  đoạn thì phải tự nói rõ ngay lúc báo cáo.
- Không tự chạy `./init.ps1` toàn bộ khi đang làm từng task — verify bằng pytest nhắm đúng
  file/test vừa sửa; chỉ chạy bộ đầy đủ ở bước nghiệm thu cuối (Task 12) hoặc khi được yêu cầu.
- Thiết kế UI bắt buộc đi qua agent thiết kế riêng (`ui-ux-pro-max` hoặc công cụ thay thế được chấp
  thuận rõ ràng) trước khi agent build khác dựng giao diện — xem mục 6.5.
- Không commit/push nếu người dùng chưa yêu cầu.

---

## 1. Mục tiêu và hành vi đã chốt

Một tổ sản xuất có `departments.is_kcs=true` đồng thời có hai cửa làm việc:

- `Tổ Thành phẩm`: xử lý các công việc sản xuất thông thường.
- `KCS · Tổ Thành phẩm`: ghi nhận kết quả kiểm tra chất lượng.

Module KCS phải đáp ứng:

- KCS theo bước routing và kiểm đột xuất công đoạn đang chạy.
- Chỉ ghi kết quả cuối đã thống nhất ngoài đời.
- Không có giao người, bấm giờ, draft, duyệt, trả lại, nhận/từ chối trách nhiệm hoặc phân xử trên phần mềm.
- Mỗi đợt chỉ nhập Đạt, Lỗi, checklist và bằng chứng.
- Cho phép ghi nhiều đợt hàng trên cùng công việc.
- KCS cuối có nút tạo yêu cầu nhập kho cho toàn bộ số đạt chưa gửi.
- Có dashboard, bộ lọc và xuất Excel hai sheet.
- Hai node dùng chung tổ, quyền, dữ liệu công việc và SSE; không tạo tổ ảo hoặc nhân đôi công việc.

## 2. Kiến trúc và mô hình dữ liệu

### 2.1. Tách "tổ có năng lực KCS" khỏi "công đoạn là KCS"

Giữ nguyên:

- `Department.is_kcs`: tổ có năng lực KCS và được sinh thêm node KCS.
- `SanXuatCongViec.la_kcs`: snapshot nói công việc đã phát hành thuộc mặt bàn KCS.
- `SanXuatCongViec.la_kcs_cuoi`: bước KCS cuối của nhóm thành phẩm.

Bổ sung:

- `CongDoan.la_kcs: bool`.
- `LsxCongDoan.la_kcs: bool`.
- `BaiGhepCongDoan.la_kcs: bool`.

Luật kế thừa:

1. Danh mục Công đoạn khai `la_kcs`.
2. Khi dựng routing LSX, cờ được snapshot xuống `LsxCongDoan`.
3. Khi gộp bước bài ghép, cờ được chép xuống `BaiGhepCongDoan`.
4. Khi phát hành, `SanXuatCongViec.la_kcs` lấy từ bước routing, không lấy từ `department.is_kcs`.
5. Một bước `la_kcs=true` chỉ hợp lệ khi phòng thực hiện có `is_kcs=true`; sai cấu hình phải chặn phát hành và chỉ rõ bước/tổ.
6. KCS cuối vẫn là đúng một bước KCS ở cuối routing của mỗi nhóm thành phẩm. Có thể có KCS trung gian.
7. Không suy KCS theo tên công đoạn.

Kết quả mong muốn:

- Bước Dán giao Tổ Thành phẩm nhưng `la_kcs=false` đi vào node sản xuất.
- Bước Kiểm tra cuối giao cùng tổ nhưng `la_kcs=true` đi vào node KCS.

### 2.2. Danh mục checklist KCS

Tạo:

- `SanXuatKcsTieuChi`
  - `id`
  - `ma`, unique
  - `ten`
  - `huong_dan`
  - `bat_buoc`
  - `thu_tu`
  - `active`
  - `version`
  - timestamps
- `SanXuatKcsTieuChiCongDoan`
  - `tieu_chi_id`
  - `cong_doan_id`
  - unique theo cặp.

Một tiêu chí có thể áp dụng cho nhiều công đoạn; một công đoạn có nhiều tiêu chí.

Gộp danh mục này vào màn Cấu hình danh mục hiện có:

- Không tạo màn danh mục riêng.
- Hỗ trợ lọc, thêm, sửa, bật/tắt và gắn nhiều công đoạn.
- Dùng hạ tầng import/export danh mục hiện có nếu cấu hình con nhiều-nhiều tương thích; nếu không, v1 chỉ chỉnh bằng UI và không mở import checklist.

Bổ sung tiêu chí riêng theo lệnh:

- `LsxCongDoan.kcs_tieu_chi_bo_sung_json`.
- `BaiGhepCongDoan.kcs_tieu_chi_bo_sung_json`.
- `SanXuatCongViec.kcs_tieu_chi_json` là snapshot đầy đủ khi phát hành.

Hình dạng snapshot:

```json
[
  {
    "tieu_chi_id": 12,
    "ma": "IN-CHONG-MAU",
    "ten": "Chồng màu đúng",
    "huong_dan": "Không lệch viền nhìn thấy",
    "bat_buoc": true,
    "nguon": "danh_muc",
    "thu_tu": 10
  },
  {
    "tieu_chi_id": null,
    "ma": null,
    "ten": "Đối chiếu mẫu màu khách duyệt ngày 28/08",
    "huong_dan": null,
    "bat_buoc": true,
    "nguon": "bo_sung_lsx",
    "thu_tu": 1000
  }
]
```

Không đọc sống danh mục khi ghi hoặc xem phiếu cũ.

### 2.3. Mở rộng kết quả KCS hiện có

Tiếp tục dùng:

- `SanXuatKcsBatch`
- `SanXuatKcsLoi`
- `SanXuatKcsLoiAnh`
- `SanXuatNhapKhoYc`

Không dựng một hệ phiếu chất lượng song song.

Bổ sung vào `SanXuatKcsBatch`:

- `loai`: `routing | dot_xuat`.
- `kcs_department_id`: tổ KCS sở hữu kết quả.
- `checklist_json`: snapshot kết quả từng tiêu chí.
- Giữ `cong_viec_id`:
  - routing: công việc KCS đã phát hành;
  - đột xuất: công việc sản xuất được kiểm.
- Giữ các cột Đạt/Không đạt hiện tại; UI đổi nhãn "Không đạt" thành "Lỗi".
- `batch_id` tiếp tục nullable nhưng kết quả mới không tạo `SanXuatBatch` năng suất.
- Các cột `bat_dau`, `ket_thuc`, `co_mau` trở thành legacy:
  - API mới không nhận chúng;
  - bản ghi mới đặt `bat_dau = ket_thuc = thời điểm máy chủ`;
  - UI và báo cáo mới dùng `created_at`;
  - tránh rebuild bảng chỉ để nullable hóa cột cũ.

Hình dạng `checklist_json`:

```json
[
  {
    "tieu_chi_id": 12,
    "ma": "IN-CHONG-MAU",
    "ten": "Chồng màu đúng",
    "ket_qua": "dat",
    "ghi_chu": null
  },
  {
    "tieu_chi_id": 18,
    "ma": "IN-LEM",
    "ten": "Không lem, không bẩn",
    "ket_qua": "khong_dat",
    "ghi_chu": "Lem mực tại mép trái"
  }
]
```

Giá trị hợp lệ của `ket_qua`:

- `dat`
- `khong_dat`
- `khong_ap_dung`

Khi `so_luong_loi > 0`:

- Bắt buộc có một `SanXuatKcsLoi`.
- Bắt buộc chọn nhóm lỗi từ danh mục `san_xuat_ly_do.nhom="loi"`.
- Bắt buộc ít nhất một ảnh.
- `to_chiu_id` và `cong_doan_ref_id` là tùy chọn vì có thể chưa thống nhất trách nhiệm ngoài đời.
- `SanXuatKcsLoi.trang_thai="recorded"` cho phiếu mới.
- Không tạo `pending`, không chờ phản hồi và không gọi luồng Nhận/Từ chối.
- Hồ sơ cũ `pending/accepted/rejected` giữ nguyên để đọc lịch sử.

## 3. Luật nghiệp vụ kết quả KCS

### 3.1. KCS theo routing

Nguồn lượng chờ KCS:

```text
lượng bàn giao đã xác nhận tới công việc KCS
− tổng so_luong_nhan của các kết quả KCS routing đã ghi
= lượng còn chờ KCS
```

Chỉ tính bàn giao trạng thái:

- `confirmed`
- `adjusted`

Không tính `proposed`.

Khi ghi kết quả:

- `Đạt >= 0`.
- `Lỗi >= 0`.
- `Đạt + Lỗi > 0`.
- `Số nhận = Đạt + Lỗi`, server tự tính.
- `Số nhận <= lượng còn chờ KCS`.
- Đơn vị lấy từ công việc/bàn giao; người dùng không chọn lại.
- Không yêu cầu công việc KCS phải Bắt đầu/Tạm dừng/Hoàn thành.
- Không tạo batch sản lượng và không phân bổ lương khoán.
- Dùng khóa hàng `SanXuatCongViec` trong transaction khi kiểm trần để hai lần lưu đồng thời không vượt lượng bàn giao.

Một công việc có thể có nhiều kết quả theo từng đợt hàng.

### 3.2. Kiểm đột xuất

Nhân viên tổ KCS được xem projection tối giản của các công việc:

- Đang chạy hoặc tạm dừng.
- Thuộc khối sản xuất.
- Gồm mã đơn/LSX, công đoạn, tổ thực hiện, máy và trạng thái.
- Không mở quyền sửa, giao người, ghi sản lượng hoặc điều khiển công việc đích.

Kết quả đột xuất:

- Chọn công việc đang chạy/tạm dừng.
- Dùng checklist snapshot của công việc đó.
- Nhập Đạt/Lỗi trong phạm vi thực tế đã kiểm.
- Không trừ lượng sản xuất, không giữ lô, không dừng việc và không tạo yêu cầu kho.
- Chỉ kiểm số không âm và tổng lớn hơn 0; không áp trần bàn giao vì đây là số quan sát, không phải dòng vật chất.

### 3.3. Thông báo

Sau khi ghi kết quả:

- Phát `san_xuat_kcs_changed` để node KCS và màn đang mở refetch.
- Nếu có `to_chiu_id`, gửi thông báo một chiều tới trưởng tổ đó:
  - nội dung nói "KCS đã ghi nhận lỗi liên quan tới tổ";
  - không tạo badge hộp thư phản hồi;
  - không có nút Nhận/Từ chối.
- Giữ xử lý SSE cũ cho hồ sơ legacy, nhưng UI mới không tạo sự kiện `san_xuat_kcs_loi` kiểu chờ phản hồi.

## 4. Quyền truy cập

### 4.1. Xem

- `san_xuat:read` + scope hiện tại quyết định các tổ và báo cáo được xem.
- Scope `all`: xem mọi node KCS và dashboard mọi tổ.
- Scope `department`: xem node trong cây phòng được phép.
- Scope `own`: xem node của chính tổ.

### 4.2. Ghi kết quả KCS

Không dùng `assign_work`.

Được ghi khi đồng thời:

- Có `san_xuat:read`.
- `user.department_id == kcs_department_id`.
- Department tồn tại và `is_kcs=true`.
- User/nhân viên còn hoạt động.

Điều này cho phép thành viên tổ KCS ghi kết quả mà không trao quyền điều phối sản xuất.

### 4.3. Điều chỉnh

Chỉ `Department.head_user_id == user.id` được điều chỉnh kết quả.

Điều chỉnh bị chặn khi:

- Có yêu cầu kho đã xác nhận dù chỉ một phần.
- Có yêu cầu kho chưa nhận nhưng chưa được hủy.

Trình tự sửa sai:

1. Hủy phần yêu cầu kho chưa nhận bằng luồng hiện có.
2. Điều chỉnh kết quả KCS.
3. Tạo lại yêu cầu kho nếu cần.

Không xóa kết quả KCS. Mọi điều chỉnh ghi audit trước/sau và kiểm `expected_version`.

### 4.4. Xuất Excel

Yêu cầu `san_xuat:export` và áp đúng scope dữ liệu như màn báo cáo.

## 5. Hợp đồng API

### 5.1. Danh sách tổ

Mở rộng `TeamOut`:

```python
class TeamOut(BaseModel):
    id: int
    ten: str
    ma: str
    la_kcs: bool
    so_viec_cho: int       # chỉ việc production chưa xong
    so_kcs_cho: int        # số công việc KCS còn lượng bàn giao chưa kiểm
```

`so_viec_cho` phải loại `SanXuatCongViec.la_kcs=true`.

`so_kcs_cho` chỉ đếm công việc:

- `la_kcs=true`;
- thuộc tổ;
- còn lượng bàn giao đã xác nhận chưa kiểm.

### 5.2. Danh sách công việc theo chế độ

Mở rộng:

```http
GET /api/san-xuat/work-items?team_id={id}&mode=production|kcs
```

- `production`: `la_kcs=false`.
- `kcs`: `la_kcs=true`.
- Thiếu `mode` mặc định `production` để frontend cũ không đột nhiên nhận việc KCS.

### 5.3. Bàn KCS

Thêm:

```http
GET /api/san-xuat/kcs/board?team_id={id}&tu=YYYY-MM-DD&den=YYYY-MM-DD
```

Trả:

- `cho_ghi`: công việc routing còn lượng chờ.
- `ket_qua`: kết quả theo bộ lọc.
- `tong_quan`: tổng lượt, tổng đạt, tổng lỗi, tỷ lệ đạt.
- `bo_loc`: danh sách công đoạn, nhóm lỗi và nguồn dữ liệu dùng cho filter.

Thêm:

```http
GET /api/san-xuat/kcs/cong-viec-dang-chay?team_id={kcs_team_id}
```

Chỉ trả projection dùng để chọn kiểm đột xuất.

### 5.4. Ghi kết quả

Thêm endpoint multipart mới, không đổi nghĩa endpoint legacy:

```http
POST /api/san-xuat/kcs/ket-qua
```

Fields:

- `loai`
- `kcs_department_id`
- `cong_viec_id`
- `so_luong_dat`
- `so_luong_loi`
- `checklist_json`
- `nhom_loi_id`, bắt buộc nếu Lỗi > 0
- `mo_ta`
- `to_chiu_id`
- `cong_doan_ref_id`
- `files[]`, bắt buộc nếu Lỗi > 0

Server tự đặt:

- số nhận;
- đơn vị;
- kết luận;
- người ghi;
- thời điểm;
- trạng thái lỗi `recorded`.

Response:

```json
{
  "kcs_batch_id": 123,
  "loai": "routing",
  "cong_viec_id": 456,
  "kcs_department_id": 8,
  "so_luong_nhan": 3000,
  "so_luong_dat": 2850,
  "so_luong_loi": 150,
  "con_lai_cho_kcs": 7000,
  "so_dat_chua_gui_kho": 2850,
  "version": 1
}
```

### 5.5. Điều chỉnh kết quả

```http
PATCH /api/san-xuat/kcs/{kcs_batch_id}
```

Body chứa:

- Đạt/Lỗi mới.
- Checklist mới.
- Thông tin lỗi cuối.
- `expected_version`.

Ảnh tiếp tục dùng endpoint thêm/xóa ảnh hiện có, nhưng không cho xóa ảnh cuối khi Lỗi > 0.

### 5.6. Tạo yêu cầu kho một nút

Thêm:

```http
POST /api/san-xuat/kcs/{kcs_batch_id}/yeu-cau-nhap-kho
```

Không nhận số lượng từ client.

Server tính:

```text
so_dat_chua_gui =
kcs_batch.so_luong_dat
− tổng yêu cầu chưa hủy của batch
```

- Chỉ cho `loai=routing`.
- Chỉ cho công việc `la_kcs_cuoi=true`.
- `so_dat_chua_gui > 0`.
- Tạo một `SanXuatNhapKhoYc` cho toàn bộ phần còn lại.
- Khóa batch trong transaction để double-click không tạo trùng.
- Nếu không còn số đạt chưa gửi, trả `409`.
- SSE tới Kho và node KCS sau commit.

### 5.7. Dashboard và Excel

```http
GET /api/san-xuat/kcs/bao-cao
GET /api/san-xuat/kcs/bao-cao/export.xlsx
```

Bộ lọc:

- `tu`, `den`
- `kcs_department_id`
- `lsx_id` hoặc từ khóa mã đơn/LSX
- `cong_doan_id`
- `loai`
- `nhom_loi_id`

Excel:

- Sheet `Kết quả KCS`: một dòng/kết quả.
- Sheet `Chi tiết checklist`: một dòng/tiêu chí/kết quả.
- Ảnh là URL.
- Freeze header, autofilter, định dạng ngày giờ theo Asia/Bangkok, số theo tối đa ba chữ số thập phân.
- Tên file: `bao-cao-kcs-YYYY-MM-DD_YYYY-MM-DD.xlsx`.

## 6. Giao diện

### 6.1. Sidebar

Trong `AppShell`:

- Node production giữ id `thuc-hien-sx:{teamId}`.
- Nếu `team.la_kcs`, thêm node `thuc-hien-kcs:{teamId}`.
- Nhãn:
  - production: tên tổ;
  - KCS: `KCS · {tên tổ}`.
- Badge:
  - production dùng `so_viec_cho`;
  - KCS dùng `so_kcs_cho`.
- SSE `san_xuat_cong_viec_changed`, `san_xuat_kcs_changed`, `san_xuat_kho` làm refetch danh sách tổ một lần; không thêm API badge riêng.

### 6.2. Màn KCS

Tạo màn danh sách-first riêng, không tái sử dụng Gantt:

- Header tên `KCS · Tổ Thành phẩm`.
- Bộ lọc gọn.
- KPI:
  - Tổng lượt.
  - Tổng Đạt.
  - Tổng Lỗi.
  - Tỷ lệ đạt.
- Biểu đồ:
  - xu hướng lỗi theo ngày/tuần;
  - nhóm lỗi nhiều nhất;
  - công đoạn/tổ được ghi nhận lỗi nhiều nhất.
- Khối `Chờ KCS`:
  - mã đơn/LSX;
  - tên sản phẩm/nhóm;
  - công đoạn;
  - lượng đã bàn giao;
  - đã kiểm;
  - còn chờ;
  - nút `Ghi kết quả`.
- Khối `Kết quả đã ghi`:
  - thời điểm;
  - Đạt/Lỗi;
  - loại routing/đột xuất;
  - trạng thái gửi kho;
  - người ghi;
  - mở drawer xem checklist/ảnh/audit.
- Nút `Kiểm đột xuất`.
- Nút `Xuất Excel` dùng bộ lọc hiện tại.

### 6.3. Form ghi kết quả

Drawer gồm:

1. Ngữ cảnh chỉ đọc: đơn/LSX, công đoạn, tổ, máy, lượng còn chờ.
2. Checklist với ba lựa chọn.
3. Hai ô số:
   - Đạt.
   - Lỗi.
4. Khi Lỗi > 0 mới hiện:
   - Nhóm lỗi.
   - Mô tả.
   - Tổ/công đoạn liên quan.
   - Ảnh bắt buộc.
5. Một nút `Lưu kết quả`.

Không hiện:

- giờ bắt đầu/kết thúc;
- cỡ mẫu;
- giao người;
- bắt đầu/tạm dừng/kết thúc;
- nút gửi duyệt;
- phản hồi trách nhiệm.

Sau khi lưu KCS cuối:

- Hiện CTA `Tạo yêu cầu nhập kho {số đạt chưa gửi}`.
- CTA chỉ một lần bấm, có busy-state chống bấm lặp.

### 6.4. KCS trong màn sản xuất cũ

- Màn production gọi `mode=production`, vì vậy không còn việc KCS trong timeline/danh sách.
- Gỡ thanh hộp thư phản hồi KCS mới khỏi trải nghiệm thường.
- Giữ khả năng đọc hồ sơ legacy tại drawer lịch sử nếu cần.
- `ThsxKhoPanel` và `ThsxDongNhomPanel` chỉ chuyển sang module KCS tại bước KCS cuối; không nhân đôi ở hai màn.

### 6.5. Thiết kế UI bắt buộc

Trước khi build:

1. Agent thiết kế riêng soi màn Thực hiện SX và pattern `RebuildCatalogPage` bằng `ui-ux-pro-max`.
2. Chốt layout danh sách, drawer, KPI, biểu đồ, mobile.
3. Agent build khác nhận đầy đủ design, dữ liệu và ràng buộc.
4. Kiểm trình duyệt thật ở desktop và 375px.
5. Chạy `styleseed-design-review` trước khi báo hoàn tất.

`ui-ux-pro-max` hiện chưa có trong môi trường; đây là điều kiện cần trước pha thiết kế UI hoặc phải có chấp thuận rõ ràng cho công cụ thay thế.

## 7. Migration và tương thích dữ liệu cũ

Không dùng Alembic.

Trong `backend/app/db_migrations.py`:

1. Thêm `la_kcs BOOLEAN NOT NULL DEFAULT false` vào:
   - `cong_doan`
   - `lsx_cong_doan`
   - `bai_ghep_cong_doan`
2. Thêm JSON checklist vào:
   - `lsx_cong_doan`
   - `bai_ghep_cong_doan`
   - `san_xuat_cong_viec`
3. Tạo hai bảng danh mục checklist.
4. Thêm `loai`, `kcs_department_id`, `checklist_json` vào `san_xuat_kcs_batch`.
5. Dùng Boolean default `false/true`, không dùng chuỗi `"0"/"1"`.
6. Backfill:
   - Tìm công việc cũ `la_kcs_cuoi=true`.
   - Theo `lsx_cong_doan_id`/`bai_ghep_cong_doan_id` để đánh dấu bước nguồn `la_kcs=true`.
   - Nếu có `cong_doan_id`, đánh dấu công đoạn danh mục tương ứng.
   - Không đánh dấu các bước khác chỉ vì department có `is_kcs=true`.
   - `kcs_department_id` của batch cũ lấy từ công việc liên kết.
   - `loai` batch cũ đặt `routing`.
   - `checklist_json` cũ để `null` hoặc `[]`.
7. Không sửa `SanXuatCongViec.la_kcs` của công việc đã phát hành.
8. Hồ sơ phản hồi cũ vẫn đọc được.
9. Cập nhật đầy đủ `docs/DB_SCHEMA.md` cùng migration.

Sau deploy:

- Admin rà lại danh mục và bật `la_kcs` cho các công đoạn KCS trung gian chưa thể backfill chắc chắn.
- Release gate hiển thị lỗi cấu hình rõ ràng nếu bước KCS chưa được khai hoặc giao sai tổ.

## 8. Trình tự triển khai theo task

### Task 1 — Migration và model nền

**Sửa/tạo chính:**

- `backend/app/models/cong_doan.py`
- `backend/app/models/lsx.py`
- `backend/app/models/bai_ghep_cong_doan.py`
- `backend/app/models/san_xuat.py`
- `backend/app/models/san_xuat_kcs.py`
- Tạo model checklist KCS và import trong `backend/app/models/__init__.py`
- `backend/app/db_migrations.py`
- `docs/DB_SCHEMA.md`

**Thực hiện:**

1. Viết test model/schema thất bại trước.
2. Thêm cột và bảng.
3. Viết migration SQLite/PostgreSQL idempotent.
4. Viết test backfill chỉ đánh dấu bước KCS cuối đã chứng minh được.
5. Kiểm migration chạy lại không lỗi.
6. Chạy `./init.ps1`.

### Task 2 — Cờ công đoạn KCS và snapshot phát hành

**Sửa chính:**

- service danh mục Công đoạn;
- service dựng routing LSX;
- `bai_ghep_service.py`;
- `services/san_xuat/snapshot.py`;
- `services/san_xuat/release.py`;
- schema/API liên quan.

**Thực hiện:**

1. Test công đoạn Dán và KCS cùng department nhưng snapshot khác `la_kcs`.
2. Test bước `la_kcs=true` giao tổ không có `is_kcs` bị chặn.
3. Test một KCS cuối/nhóm được phát hành.
4. Test thiếu hoặc nhiều KCS cuối bị chặn.
5. Test KCS trung gian không bị đánh thành KCS cuối.
6. Thay mọi suy luận `department_id in kcs_depts` bằng cờ bước + validation tổ.
7. Chạy `./init.ps1`.

### Task 3 — Danh mục checklist và snapshot theo lệnh

**Sửa/tạo chính:**

- model/repository/service/schema checklist;
- đăng ký trong Cấu hình danh mục;
- routing LSX/bài ghép;
- snapshot công việc.

**Thực hiện:**

1. Test nhiều tiêu chí/một công đoạn và một tiêu chí/nhiều công đoạn.
2. Test chỉ tiêu chí active được snapshot.
3. Test tiêu chí bổ sung LSX được nối sau checklist chuẩn.
4. Test đổi danh mục sau phát hành không đổi snapshot công việc.
5. Thêm UI cấu hình và trường bổ sung trong drawer bước LSX hiện có.
6. Chạy `./init.ps1`.

### Task 4 — Tách board production/KCS và hai badge

**Sửa chính:**

- `repositories/san_xuat_repo.py`
- `services/san_xuat/board.py`
- `schemas/san_xuat.py`
- `routers/san_xuat.py`
- `frontend/src/api/client.ts`
- `frontend/src/components/AppShell.tsx`

**Thực hiện:**

1. Test `mode=production` chỉ trả `la_kcs=false`.
2. Test `mode=kcs` chỉ trả `la_kcs=true`.
3. Test thiếu mode mặc định production.
4. Test badge production không đếm KCS.
5. Test badge KCS chỉ đếm việc còn bàn giao xác nhận chưa kiểm.
6. Sinh node `KCS · {tổ}` chỉ khi `la_kcs=true`.
7. Chạy `./init.ps1`.

### Task 5 — Service ghi kết quả routing và đột xuất

**Sửa chính:**

- `repositories/san_xuat_kcs_repo.py`
- `services/san_xuat/kcs.py`
- `schemas/san_xuat.py`
- `routers/san_xuat.py`
- tests KCS.

**Thực hiện:**

1. Thay gate tổ trưởng bằng gate thành viên tổ KCS cho endpoint mới.
2. Viết test routing nhiều đợt.
3. Test tổng đợt không vượt bàn giao confirmed/adjusted.
4. Test proposed không tạo lượng chờ.
5. Test không cần khởi động công việc KCS.
6. Test không tạo `SanXuatBatch` năng suất.
7. Test checklist bắt buộc đủ kết quả.
8. Test Lỗi > 0 bắt nhóm lỗi và ảnh.
9. Test Đạt/Lỗi không âm và tổng lớn hơn 0.
10. Test đột xuất chỉ chọn việc running/paused.
11. Test đột xuất không sửa sản lượng/trạng thái/kho.
12. Test ngoài tổ KCS bị 403.
13. Chạy `./init.ps1`.

### Task 6 — Điều chỉnh có audit

**Thực hiện:**

1. Test chỉ trưởng tổ KCS được sửa.
2. Test `expected_version` sai bị chặn.
3. Test sửa trước khi gửi kho thành công.
4. Test có yêu cầu kho chưa hủy bị chặn.
5. Test kho đã nhận một phần bị chặn tuyệt đối.
6. Test ảnh cuối không được xóa nếu kết quả còn lỗi.
7. Ghi audit trước/sau.
8. Chạy `./init.ps1`.

### Task 7 — Yêu cầu nhập kho một nút

**Sửa chính:**

- `services/san_xuat/kho.py`
- `repositories/san_xuat_kho_repo.py`
- router/schema KCS–Kho.

**Thực hiện:**

1. Test chỉ KCS cuối routing được gửi kho.
2. Test tự lấy toàn bộ số đạt chưa gửi.
3. Test lần bấm thứ hai không tạo trùng.
4. Test batch đạt một phần vẫn gửi đúng số đạt.
5. Test kiểm đột xuất không được gửi kho.
6. Test transaction khóa batch chống hai request đồng thời.
7. Test Kho xác nhận từng phần vẫn hoạt động như cũ.
8. Chạy `./init.ps1`.

### Task 8 — Báo cáo và Excel

**Tạo/tách riêng service báo cáo KCS** để không làm `kcs.py` phình thêm.

**Thực hiện:**

1. Viết query tổng hợp theo filter và scope.
2. Tỷ lệ đạt dùng tổng Đạt / tổng nhận, không lấy trung bình tỷ lệ từng phiếu.
3. Nhóm lỗi/công đoạn/tổ xếp theo tổng số lỗi.
4. Hồ sơ không xác định trách nhiệm không được gán vào tổ.
5. Tạo workbook hai sheet.
6. Test tên sheet, header, số dòng, filter và URL ảnh.
7. Test quyền export và scope.
8. Chạy `./init.ps1`.

### Task 9 — Màn KCS và form tối giản

**Tạo mới dự kiến:**

- `frontend/src/pages/kcs/ThucHienKcsPage.tsx`
- `frontend/src/pages/kcs/KcsResultDrawer.tsx`
- `frontend/src/pages/kcs/KcsDashboard.tsx`
- `frontend/src/pages/kcs/kcs.css`

**Sửa:**

- `AppShell.tsx`
- `client.ts`
- các component KCS cũ trong `ThsxG5.tsx`/`ThsxDrawer.tsx`.

**Thực hiện:**

1. Dựng trang list-first theo design đã duyệt.
2. Dựng khối Chờ KCS và lịch sử.
3. Dựng form bốn bước tối giản.
4. Ẩn khối lỗi khi Lỗi = 0.
5. Validate checklist và ảnh phía client nhưng vẫn tin backend là trọng tài.
6. Dựng chọn công việc kiểm đột xuất.
7. Dựng CTA nhập kho một nút.
8. Dựng drawer lịch sử và audit.
9. Dựng loading/error/empty state riêng, không báo "không có dữ liệu" khi API lỗi.
10. Kiểm desktop và 375px bằng browser thật.

### Task 10 — Dashboard, filter và tải Excel

**Thực hiện:**

1. Đồng bộ một bộ filter cho KPI, biểu đồ, lịch sử và URL Excel.
2. Không tính lại KPI ở frontend; dùng số backend.
3. Biểu đồ chỉ hiển thị quan hệ cần thiết, không thêm card trang trí.
4. Nút Excel giữ nguyên filter hiện tại.
5. Kiểm dữ liệu không có lỗi, chỉ có lỗi, nhiều tổ và nhiều đơn.
6. Kiểm mobile không làm biểu đồ ép tràn trang.

### Task 11 — SSE và legacy cleanup

**Thực hiện:**

1. Mở rộng payload `san_xuat_kcs_changed` với `team_id`, `kcs_batch_id`, `loai`.
2. AppShell refetch team list để hai badge cập nhật.
3. Trang KCS đang mở refetch board sau sự kiện đúng tổ.
4. Thông báo tổ liên quan là một chiều.
5. Gỡ hộp thư phản hồi khỏi UI mới.
6. Giữ endpoint và kiểu dữ liệu legacy để đọc hồ sơ cũ.
7. Test không cần refresh thủ công.

### Task 12 — Tài liệu và nghiệm thu cuối

**Cập nhật:**

- `docs/spec-thuc-hien-san-xuat.md`
- `docs/DB_SCHEMA.md`
- tài liệu hướng dẫn sử dụng liên quan.

**Nội dung:**

- Hai module trên cùng tổ.
- Phân biệt cờ tổ/cờ bước.
- Checklist.
- Routing/đột xuất.
- Luồng chỉ ghi kết quả cuối.
- Gửi kho một nút.
- Dashboard/Excel.
- Luồng legacy không còn áp dụng cho phiếu mới.

**Xác minh cuối:**

1. Restart uvicorn sau thay route/schema.
2. Chạy `./init.ps1` và lưu kết quả thật.
3. Kiểm browser:
   - hai node;
   - badge;
   - ghi nhiều đợt;
   - lỗi + ảnh;
   - kiểm đột xuất;
   - gửi kho;
   - dashboard;
   - Excel;
   - SSE.
4. Agent thiết kế và agent build phải là hai agent khác nhau.
5. Chạy `styleseed-design-review`.
6. Không commit hoặc push nếu người dùng chưa yêu cầu.

## 9. Kịch bản nghiệm thu bắt buộc

1. Tổ Thành phẩm có cờ KCS:
   - node Tổ Thành phẩm có việc Dán;
   - node KCS có việc Kiểm cuối;
   - không có việc xuất hiện ở cả hai node.
2. Bàn giao 3.000:
   - ghi Đạt 2.850, Lỗi 150;
   - còn chờ giảm đúng 3.000;
   - badge KCS cập nhật ngay.
3. Lỗi 150:
   - không có ảnh thì không lưu;
   - có ảnh và nhóm lỗi thì lưu;
   - tổ liên quan nhận thông báo một chiều.
4. Bấm tạo yêu cầu kho:
   - tạo đúng 2.850;
   - bấm lại không tạo trùng;
   - Kho xác nhận 2.000 rồi 850 vẫn đúng.
5. Đợt thứ hai được ghi độc lập và tổng cộng đúng.
6. Kiểm đột xuất công đoạn In:
   - lưu checklist và Đạt/Lỗi;
   - không đổi sản lượng In;
   - không đổi trạng thái công việc;
   - không hiện nút nhập kho.
7. Nhân viên tổ KCS ghi được; người ngoài tổ không ghi được.
8. Trưởng KCS sửa được trước gửi kho; nhân viên thường không sửa.
9. Checklist danh mục đổi sau phát hành nhưng phiếu cũ không đổi.
10. Dashboard và Excel cho cùng filter trả cùng tổng.
11. Phiếu legacy vẫn xem được nhưng không ép người dùng mới vào luồng phản hồi cũ.
12. SQLite dev và PostgreSQL-compatible migration đều dùng default Boolean hợp lệ.

## 10. Ngoài phạm vi

- Không phân xử tranh chấp trên phần mềm.
- Không có workflow Nhận/Từ chối trách nhiệm cho phiếu mới.
- Không tự dừng máy, giữ lô hoặc mở LSX bù.
- Không thống kê lấy mẫu hoặc suy tỷ lệ lỗi toàn lô.
- Không nhập thông số đo/dung sai.
- Không chấm giờ, giao người, tính năng suất hoặc lương khoán KCS.
- Không tự động tạo yêu cầu kho ngay khi lưu; người dùng phải bấm nút.
- Không hồi tố lại loại công việc đã phát hành.
- Không commit/push nếu chưa được yêu cầu.
