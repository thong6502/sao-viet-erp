# Spec — Thực tế sản xuất phản hồi về Kế hoạch

> Nguồn: rà soát 30–31/08/2026 trả lời câu hỏi *"logic hiện tại đã phủ việc chia sản lượng và
> liên quan tới xếp lịch công đoạn chưa, khi thực tế khác kế hoạch?"*. Đây là spec THIẾT KẾ —
> code chưa làm. Plan thi công: `docs/superpowers/plans/2026-08-31-thuc-te-phan-hoi-ke-hoach.md`
> và `docs/superpowers/plans/2026-08-31-tach-lan-chay-cong-doan.md`.

## 1. Hiện trạng (đã kiểm bằng code, 31/08/2026)

Hệ có ĐỦ dữ liệu thực tế, nhưng dữ liệu đó **chỉ chảy một chiều vào tầng thực thi rồi dừng lại**.

| Có sẵn | Ở đâu |
| --- | --- |
| Giờ chạy thật từng phiên | `san_xuat_phien_chay.bat_dau/ket_thuc` |
| Sản lượng tốt / hỏng từng mẻ | `san_xuat_batch.tot/hong` (`_EPS = 0.0005`, `tong = tot + hong`) |
| Toả sản lượng bài ghép sang LSX nhánh | `services/san_xuat/san_luong.py::_toa_san_luong` — `sl_nhanh = round(tot * ty_le_ghep, 3)` |
| Chia công khoán theo người | `services/san_xuat/phan_bo.py` (phút × hệ số bậc, làm tròn dư lớn nhất) |
| Bàn giao giữa công đoạn | `san_xuat_ban_giao`, trần = `tong_tot` |

Ba chỗ HỔNG:

### 1.1 Người lập kế hoạch mù trước thực tế
`services/xep_lich_2/service.py::workspace()` (dòng 974) dựng bàn Gantt CHỈ từ
`xep_lich_cong_doan`. `_dong_view(r, nhan)` (dòng 894) trả 20 khoá, **không khoá nào chạm
`san_xuat_*`**. Danh sách import của module (dòng 21–36) không có gì từ `san_xuat`.
`XepLich2Page.tsx` không hề nhắc `thuc_te` / `san_luong` / `tong_tot`.

Chiều ngược lại thì có: `repositories/san_xuat_repo.py:205 thoi_gian_lsx_step()` và `:212
thoi_gian_bg_step()` đọc `XepLichCongDoan.may_id/start_at/finish_at` — nhưng chỉ ĐỌC MỘT LẦN lúc
snapshot phát hành.

Hệ quả: bước in chậm 6 tiếng, mọi bước sau trên Gantt vẫn nằm nguyên chỗ cũ. Nhãn rủi ro
(`xep_lich_service.py:1257-1314 _chuoi()`) tính CPM thuần trên `finish_at` KẾ HOẠCH;
`override_finish` chỉ được bơm bởi xem-trước kéo-thả (dòng 1739), **không bao giờ bởi số thật**.

12 bộ dò của `xep_lich_van_de_service.py` không có bộ nào tên `thuc_te`.

`docs/spec-thuc-hien-san-xuat.md:184` đã ghi *"Sai lệch kế hoạch được phản ánh lại cho bộ phận
lập kế hoạch"* — câu đó CHƯA cài đặt.

### 1.2 Không có con số "còn thiếu"
`services/san_xuat/dong_nhom.py::_danh_gia` dựng 6 điều kiện đóng nhóm. Chú thích dòng 63 nói rõ
KCS cuối đo bằng **đã phân loại / đã nhận**, *"KHÔNG so với mục tiêu đơn"* — đây là quyết định
sản phẩm CỐ Ý, không phải bug. Nhưng hệ quả là: đơn đặt 10.000, chạy ra 9.400 tốt → nhóm vẫn
"đủ đóng", không chỗ nào hiện số **600**.

`SanXuatCongViec.so_luong_ra` (snapshot mục tiêu của bước, đúng đơn vị ra) đã có sẵn và chưa ai
đem so với `tong_tot`.

`docs/spec-thuc-hien-san-xuat.md` §13.3 và §22 chốt: không tự sinh luồng sửa hàng, không tự tạo
LSX bù. Con số "còn thiếu" vì vậy chỉ để **BÀY**, không kéo theo hành động máy.

### 1.3 Không tách được lần chạy
`models/xep_lich.py:55 XepLichCongDoan` **không có cột số lượng**. Một công đoạn = một thanh, một
khoảng giờ, một máy. Không cách nào diễn đạt "in 10.000 tờ: 6.000 hôm nay máy A, 4.000 mai máy B".

Tầng thực thi thì tách được (nhiều `SanXuatBatch` cho một công việc — docstring `tao_batch` ghi
*"Cho nhiều batch một phần / công đoạn"*), nhưng tầng kế hoạch không biết chuyện đó.

Chặn cứng phía trên: `lsx_service.py:1441 tao()` — `"Dòng đã có lệnh sản xuất — không tạo trùng"`
⇒ không tách được bằng cách đẻ hai LSX cho một dòng đơn.

`snapshot.py::dung_cong_viec` dựng `cv_by_step: dict[str, SanXuatCongViec]` — **một công việc cho
một `step_key`**. Đây là nút thắt thật của việc tách lần chạy, không phải cột số lượng.

## 2. Quyết định thiết kế

### 2.1 Lớp thực tế đè lên Gantt — CHỈ ĐỌC
Máy **không tự dời thanh**. `XepLichCongDoan` vốn là "record-only: máy đề xuất, người quyết"
(docstring dòng 87); tự động đẩy lịch theo thực tế sẽ phá đúng nguyên tắc đó và phá cả
`is_locked`. Thực tế chỉ hiện thành **lớp đè trong thanh** + **một bộ dò mới**; người điều độ
nhìn rồi tự kéo.

Nối hai tầng bằng cặp neo đã có:
`XepLichCongDoan.lsx_cong_doan_id` ↔ `SanXuatCongViec.lsx_cong_doan_id`, và
`XepLichCongDoan.bai_ghep_cong_doan_id` ↔ `SanXuatCongViec.bai_ghep_cong_doan_id`.
Nạp GỘP một lượt như `_nap_nhan` đang làm — không N+1.

Chỉ lấy công việc của **phiên bản gói đang hiệu lực**; công việc thuộc phiên bản cũ bỏ qua.

### 2.2 Bộ dò thứ 13 — `lech_thuc_te`
- `issue_key` = `f"lech_thuc_te:{xep_lich_cong_doan_id}"` (mịn theo dòng lịch, như 12 bộ dò cũ).
- `category` = `CAT_HAN` (trễ hạn giao là hệ quả người ta quan tâm).
- `severity` = `SEV_LUU_Y`. **Không bao giờ `SEV_CHAN`** — thực tế lệch không được chặn phát hành:
  lệnh đã phát hành rồi mới có thực tế, chặn ở đây là chặn muộn và vô nghĩa.
- Bắn khi một trong hai:
  - đã bắt đầu MUỘN hơn `du_kien_bat_dau` quá `NGUONG_LECH_THUC_TE_PHUT = 60`;
  - đang chạy (`dang_chay`) mà đã quá `du_kien_ket_thuc` quá cùng ngưỡng đó.
- `delay_phut` = số phút lệch lớn nhất trong hai vế → hàng đèn Kế hoạch SX cộng dồn được.

### 2.3 "Còn thiếu" là số DẪN XUẤT, không lưu
- Mức công đoạn: `con_thieu = max(so_luong_ra - tong_tot, 0)` (cùng `don_vi_ra`).
- Mức nhóm thành phẩm: mục tiêu = `Σ so_luong_ra` của các công việc **KCS cuối** trong nhóm;
  đạt được = `Σ tong_tot` của chính các công việc đó.
- **KHÔNG đổi cổng đóng nhóm.** `_danh_gia` giữ nguyên 6 điều kiện. Con số chỉ đi kèm để người
  bấm "đóng thiếu" nhìn thấy mình đang thiếu bao nhiêu — hiện tại họ bấm mù.
- Không lưu cột mới, không bảng mới: lưu thành cột là mời sai lệch (cùng lý do
  `stock_request_lines` cố ý không lưu "còn lại").

### 2.4 Tách lần chạy — làm sau, hai pha
Đây là thay đổi kiến trúc, không phải một cột. Tách hẳn thành plan riêng vì:
1. `xep_lich_cong_doan` phải mọc chiều SỐ LƯỢNG (`so_luong`, `phan_doan_so`, `phan_doan_tong`,
   `goc_dong_id`).
2. Engine thời lượng phải chia tỉ lệ theo phần.
3. `thoi_gian_lsx_step()` / `thoi_gian_bg_step()` đang trả **một** bộ (máy, giờ) cho một công
   đoạn — phải trả danh sách.
4. `dung_cong_viec()` phải đẻ **một `SanXuatCongViec` cho mỗi phân đoạn**, và `cv_by_step` từ
   `dict[str, cv]` thành `dict[str, list[cv]]`; `dung_phu_thuoc` phải nối chuỗi trong-phân-đoạn.
5. `dong_nhom`, `ban_giao`, `phan_bo` đều đếm theo công việc → tự động đúng khi (4) đúng, nhưng
   phải có test chứng minh.

Pha 1 = (1)(2)(3) + UI tách/gộp trên bàn xếp lịch, chưa phát hành.
Pha 2 = (4)(5) + phát hành nhiều phân đoạn.

## 3. Ngoài phạm vi
- Không tự dời lịch theo thực tế.
- Không tự sinh LSX bù / lệnh sửa hàng (`spec-thuc-hien-san-xuat.md` §22 đã chốt).
- Không cho tổ trưởng kéo sửa lịch (§22).
- Không sửa cổng đóng nhóm.
- Không đụng module vật tư — chuyện đó nằm ở `docs/spec-de-nghi-cap-vat-tu-cong-doan.md`.
