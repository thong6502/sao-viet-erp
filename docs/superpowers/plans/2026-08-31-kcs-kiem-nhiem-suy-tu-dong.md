# Bản sửa: bỏ cờ khai tay `la_kcs`, suy KCS cuối tự động từ tổ thực hiện

> Đây là bản SỬA cho `docs/superpowers/plans/2026-08-31-kcs-kiem-nhiem.md` (đã implement xong
> Task 1-11.5, đang ở Task 12 nghiệm thu). KHÔNG viết lại từ đầu — chỉ đổi phần suy cờ KCS.
> Trạng thái: ĐÃ LÀM XONG + đã verify UI thật trên dev-browser (2026-08-31/09-01) — xem ghi chú
> nghiệm thu ở cuối file.

## Quyết định đã chốt (2026-08-31, xác nhận với user)

Xưởng chỉ có 2 loại KCS:
1. **Ngẫu nhiên** — tổ KCS kiểm bất kỳ công đoạn nào, bất kỳ lúc nào. Đã có sẵn, đúng ý, KHÔNG đổi
   ("Kiểm đột xuất" — `tao_kiem_dot_xuat`, `backend/app/services/san_xuat/kcs.py:253`).
2. **Cuối** — tổ Thành phẩm (hoặc bất kỳ tổ nào đang giữ bước cuối) làm xong bước CUỐI của quy
   trình một lệnh, kiểm rồi tạo yêu cầu nhập kho.

Với loại 2: **bỏ hẳn việc phải khai tay "công đoạn này là KCS" trên danh mục.** Thay bằng suy tự
động — bước CUỐI CÙNG trong routing của một LSX, nếu TỔ thực hiện bước đó có bật
`Department.is_kcs=true` ("Tổ KCS đích danh" — toggle đã có sẵn UI ở màn Phòng ban), thì bước đó
tự động là bước KCS cuối. Không cần đánh dấu tay bước nào cả.

## Vì sao đổi (bối cảnh phát hiện ra khi nghiệm thu Task 12)

Bản thiết kế gốc (`2026-08-31-kcs-kiem-nhiem.md` §2.1) tách hai khái niệm: "tổ có năng lực KCS"
(`Department.is_kcs`) và "công đoạn này là bước KCS" (`CongDoan.la_kcs`, khai riêng ở danh mục).
Lý do lúc đó: dự trù một tổ có thể vừa làm bước KCS vừa làm bước thường trong CÙNG một đơn (ví dụ
Tổ Thành phẩm: bước "Dán" không cần kiểm, bước "Kiểm tra cuối" cần kiểm).

Khi nghiệm thu UI thật mới phát hiện: **Task 1 dự kiến có một ô trên danh mục Công đoạn để khai
`la_kcs`, nhưng ô đó chưa từng được build** — grep toàn bộ frontend không thấy field nào cho phép
bật cờ này. Cờ chỉ có giá trị `true` nhờ một migration backfill một lần từ dữ liệu lịch sử
(`db_migrations.py` — `0251_kcs_kiem_nhiem_backfill_la_kcs`), không có đường sống nào để tạo mới.
Nghĩa là tính năng "KCS cuối" hiện KHÔNG dùng được qua UI thật với công đoạn mới.

Hỏi lại thực tế xưởng thì tình huống "một tổ vừa có bước KCS vừa có bước thường trong cùng đơn"
KHÔNG xảy ra — nên cờ khai tay là thừa, và suy tự động từ tổ đơn giản hơn hẳn, dùng đúng cái toggle
đã có UI sẵn.

## Thay đổi cụ thể

### 1. `backend/app/services/san_xuat/snapshot.py`

- `dung_cong_viec()` (dòng 80-158): thêm tham số `kcs_dept_ids: set[int]`. Tại hai chỗ đang set
  `la_kcs=bool(cd.la_kcs)` (dòng 118, 145) — đổi thành tính trực tiếp: bước này có phải bước CUỐI
  của LSX chứa nó (`cd.step_key == steps[-1].step_key`, với `steps = repo.routing_steps(lsx_id)`)
  VÀ `cd.department_id in kcs_dept_ids`. Vì bước dùng chung của bài ghép (phần (1), dòng 100-131)
  có thể phủ nhiều LSX, cần kiểm "là bước cuối" trên TỪNG LSX bị phủ, không chỉ một.
- `danh_dau_kcs_cuoi()` (dòng 161-193): đổi điều kiện ứng viên dòng 183 từ `cuoi.la_kcs` sang
  `cuoi.department_id in kcs_dept_ids`. Giữ nguyên phần còn lại (gom theo nhóm, chặn khi 0 hoặc
  ≥2 ứng viên) — luật "đúng một bước KCS cuối mỗi nhóm" không đổi, chỉ đổi tiêu chí nhận diện
  ứng viên.
- `_checklist()` (dòng 61-77): đổi tham số nhận `la_kcs: bool` đã tính sẵn từ ngoài (cùng logic
  trên) thay vì tự đọc `cd.la_kcs` ở dòng 64.

### 2. `backend/app/services/san_xuat/release.py`

- `van_de_phat_hanh()`:
  - Dòng 148 (`if steps and steps[-1].la_kcs:`) đổi thành
    `if steps and steps[-1].department_id in kcs:` (biến `kcs` = `repo.kcs_department_ids()` đã
    có sẵn ở dòng 125, khỏi cần thêm truy vấn).
  - **Bỏ hẳn Luật 5** (dòng 164-179, mã lỗi `kcs_sai_to`): luật này chặn "bước khai la_kcs nhưng tổ
    không có năng lực KCS" — chỉ có thể xảy ra khi la_kcs khai tay lệch với tổ. Sau khi la_kcs suy
    thẳng từ tổ, tình huống này không còn xảy ra được nữa nên luật hết tác dụng.

### 3. `backend/app/services/lsx_service.py`

- `_default_buoc` (dòng ~1411): bỏ `"la_kcs": bool(cd_obj.la_kcs) if cd_obj else False` — không
  còn cột nguồn để đọc (xem mục 5).
- `_cong_doan_dict` (dòng 2221-2242): đổi field trả về `"la_kcs"` (dòng 2242) từ đọc `cd.la_kcs`
  sang tính theo cùng logic mới, để FE (LsxBuocDrawer) vẫn hiện đúng khối "Tiêu chí KCS bổ sung"
  ngay lúc lập kế hoạch — TRƯỚC khi phát hành. Khác trước ở chỗ: giá trị này giờ phản ánh trạng
  thái SỐNG (đổi tổ thực hiện bước cuối → hiện/ẩn khối ngay), không phải cờ đã lưu tĩnh — chấp
  nhận được vì đây chỉ là gợi ý cho người lập kế hoạch, số THẬT vẫn chốt lại một lần lúc snapshot
  phát hành (mục 1).
- `_ROUTING_FIELD_THUAN` (dòng 2691-2707): bỏ `"la_kcs"` khỏi danh sách field PUT /routing nhận
  ghi đè từ client (dòng 2702) — không còn ý nghĩa để sửa tay, và cũng không còn cột để ghi vào.

### 4. `backend/app/services/bai_ghep_service.py`

- Dòng ~762-763: bỏ `la_kcs=bool(mau.la_kcs)` khi copy mẫu bước bài ghép — hết field nguồn.

### 5. Model + schema + migration

- Bỏ cột `la_kcs` khỏi 3 bảng: `CongDoan` (`models/cong_doan.py`), `LsxCongDoan` (`models/lsx.py`),
  `BaiGhepCongDoan` (`models/bai_ghep_cong_doan.py`) — không dùng để lưu nữa, chỉ còn ý nghĩa tính
  lúc đọc.
- Migration MỚI trong `db_migrations.py` (không sửa `0251` cũ — giữ nguyên lịch sử): `DROP COLUMN`
  cả ba, đặt SAU `0251` trong thứ tự chạy.
- Bỏ 3 cột này khỏi `docs/DB_SCHEMA.md` (guard test đòi khớp model ↔ doc).
- Bỏ field `la_kcs` khỏi schema tương ứng: `schemas/cong_doan.py`, `schemas/lsx.py`.

### 6. Frontend

- `frontend/src/pages/LsxBuocDrawer.tsx:654` — điều kiện hiện khối "Tiêu chí KCS bổ sung" đọc
  `row.la_kcs` — GIỮ NGUYÊN, không cần sửa (tên field response không đổi, chỉ nguồn tính ở BE đổi).
- `frontend/src/pages/lsxBuoc.ts:321-323` — comment nói rõ KHÔNG gửi `la_kcs` lên PUT /routing —
  giữ nguyên (đúng hướng, giờ càng không cần gửi vì BE không còn nhận field này).
- **Không cần thêm màn khai `la_kcs` trên danh mục Công đoạn** — đây chính là phần ĐƠN GIẢN HOÁ so
  với bản gốc (Task 1 cũ dự tính phải xây UI đó, giờ bỏ hẳn).

### 7. Test cần sửa (biết trước, rà thêm lúc làm)

`test_san_xuat_kcs.py`, `test_san_xuat_g5_tich_hop.py`, test snapshot/release liên quan
`la_kcs`/`la_kcs_cuoi` hiện dựng dữ liệu bằng cách gán cờ tay trên `LsxCongDoan.la_kcs` — phải đổi
sang dựng bằng cách gán `department_id` của bước CUỐI trỏ tới một phòng có `is_kcs=true`.

## Giữ nguyên, không đổi

- `SanXuatCongViec.la_kcs`, `la_kcs_cuoi` (cột trên bảng công việc đã phát hành) — GIỮ cấu trúc,
  chỉ đổi NGUỒN suy ra giá trị lúc snapshot.
- `Department.is_kcs` + toggle "Tổ KCS đích danh" ở màn Phòng ban — GIỮ NGUYÊN, đã là nguồn thật
  cho suy luận mới.
- `tao_kiem_dot_xuat` (Kiểm đột xuất) — GIỮ NGUYÊN.
- `board.py` (tách bảng "sản xuất"/"KCS" theo tổ), `dong_nhom.py` (điều kiện đóng nhóm),
  `kcs.py::tao_batch_kcs` (ghi batch kiểm routing) — đọc `cv.la_kcs`/`la_kcs_cuoi` như cũ, không
  đổi gì (chỉ nguồn GHI vào hai cột đó lúc snapshot đổi, cách ĐỌC sau phát hành giữ nguyên).
- Danh mục checklist KCS (`SanXuatKcsTieuChi`, Task 5+) — giữ nguyên, chỉ đổi điều kiện "bước này
  có phải KCS" dùng để quyết định có ghép checklist vào bước hay không (mục 1).

## Rủi ro đã biết, xin xác nhận lại nếu phát sinh

- Nhóm thành phẩm có nhiều LSX thành viên, ≥2 LSX cùng kết thúc bằng bước do tổ KCS làm → vẫn mập
  mờ "lệnh thân chính", vẫn CHẶN PHÁT HÀNH như luật cũ (chỉ đổi tiêu chí nhận diện ứng viên, không
  đổi hành vi chặn).
- Nếu một tổ có bật `is_kcs=true` được giao làm bước CUỐI nhưng bước đó thực chất không nhằm mục
  đích kiểm (ví dụ chỉ đóng gói thuần tuý) → hệ thống sẽ tự động coi đó là bước KCS. Rủi ro này
  ĐÃ ĐƯỢC XÁC NHẬN CHẤP NHẬN trong buổi bàn 2026-08-31 (xưởng khẳng định không có tình huống này
  trong thực tế) — ghi lại để đối chiếu nếu sau này phát sinh ca thật.

## Nghiệm thu — verify UI thật trên dev-browser (2026-08-31 → 2026-09-01)

Migration `0252` chạy sạch trên Postgres dev thật (`svn_erp_local`, cổng 5433) lúc uvicorn khởi
động — kiểm bằng cách vào Danh mục Công đoạn/LSX routing, không còn cột `la_kcs` khai tay. Backend
:8030 + frontend :5190 riêng cho worktree này, đăng nhập `admin`/`admin123`.

Kịch bản thao tác tay:
1. LSX26-0032 (đơn DH034, đã "Sẵn sàng lập kế hoạch") — vào tab Công đoạn, chèn thêm bước "Kiểm
   tra chất lượng (KCS)" (CD-0015) sau bước "Cán màng bóng". Bấm Lưu công đoạn.
2. Mở lại bước KCS vừa chèn (tab Phân công & Thiết bị): "TỔ PHỤ TRÁCH" hiện **Tổ Tổ thành phẩm**
   — đúng phòng ban đã bật `is_kcs=true` (xác nhận trước đó qua màn Phòng ban: PB013 Tổ thành
   phẩm = ON, PB015 Tổ KCS chính nó = OFF). Backend tự resolve từ `CongDoan.department_id` của
   danh mục CD-0015 khi client không gửi `department_id` tường minh (`lsx_service.py:2758`).
2b. Mở bước KCS: panel "TIÊU CHÍ KCS BỔ SUNG" xuất hiện. Mở lại bước 01/02 "Cán màng bóng"
   (không phải bước cuối): KHÔNG có panel này — đúng chiều suy diễn "bước cuối + is_kcs".
3. Vào Xếp lịch công đoạn 2 → tìm LSX26-0032 → "Đưa vào kế hoạch" → "Xếp các bước còn trống" (xếp
   được 2/2 bước lên máy Cán màng 800×1080). Bấm "Phát hành": banner chỉ báo MỘT chặn —
   `vat_tu_chua_du` (thiếu vật tư Màng cán bóng, không liên quan KCS). KHÔNG còn banner "Luật 5"
   nào về lệch tổ/KCS như bản cũ — xác nhận đã gỡ hẳn.
4. Không đi tiếp qua cổng thiếu vật tư (chạm dữ liệu tồn kho thật, ngoài phạm vi revision này).
   Thay vào đó đối chiếu trên dữ liệu SẢN XUẤT THẬT đã có sẵn: màn "KCS · Tổ thành phẩm" (board
   theo tổ, derive từ `SanXuatCongViec.la_kcs`) hiện thống kê thật — Tổng lượt 5, Tổng đạt 144,
   Tổng lỗi 20, tỷ lệ đạt 87.8% — chứng minh suy luận mới đang chạy đúng trên các lệnh đã phát
   hành từ trước, không chỉ trên lý thuyết.
5. Dọn dẹp: bấm "Nhả chỗ giữ" ở Kế hoạch vật tư cho LSX26-0032 — trả lại 61.950 m2 Màng cán bóng
   + 15,26 kg Couché 300 65×86 vào tồn kho chung (đã giữ tạm ở bước 3 khi test xếp lịch), tránh để
   lại giữ chỗ ma trên dữ liệu dev thật. LSX26-0032 tự động mất chỗ xếp lịch theo cảnh báo khi nhả.

Không dùng curl/API thay bước nào trong luồng trọng tâm (chèn bước KCS → lưu routing → xếp lịch →
kiểm banner phát hành → đọc board KCS thật). Có một khoảng gián đoạn ngoài ý muốn giữa bước 3 và 4
— dev-browser bị đăng xuất (phiên hết hạn tự nhiên, không phải do sửa code), phải đăng nhập lại
`admin`/`admin123` hai lần qua UI thật (không phải request tay) mới tiếp tục được.

Test suite: sửa 1 test sai giả định (`test_gop_giu_department_id_buoc_mau` —
[test_bai_ghep_service.py](../../../backend/tests/test_bai_ghep_service.py) — gán nhầm việc `gop()`
phải chép `department_id` xuống `BaiGhepCongDoan`, trong khi `gop()` cố ý KHÔNG chép và suy KCS
cũng không đọc cột đó). Xoá test này; `pytest tests/test_bai_ghep_service.py -q` → 49 passed.
