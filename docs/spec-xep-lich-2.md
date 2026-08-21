# SPEC — XẾP LỊCH CÔNG ĐOẠN 2

> Màn thứ hai của pha xếp lịch, nằm ngay dưới màn cũ, khoá quyền riêng `xep_lich_2`. UI + engine
> điều phối viết MỚI; lịch vẫn lưu vào `xep_lich_cong_doan` — **một lịch thật, hai cửa vào**.
> Anh em: `spec-cong-doan.md`, `spec-bai-ghep-dag.md`, `spec-thue-ngoai-giao-nhan.md`.
> Precedent tổ chức module: `bai_ghep_2` (dùng chung engine/bảng, tách lớp HTTP + ô quyền).

---

## 1. Vì sao có màn 2

Màn cũ đúng ở tầng dữ liệu nhưng chia người dùng ra ba bàn rời (Bảng · Gantt · Vấn đề), và luật
xếp lịch của nó pha tạp: có chỗ chặn, có chỗ chỉ cảnh báo, và nó tự cắt việc theo ca nên giờ kết
thúc không giống thực tế xưởng. Màn 2 làm lại đúng ba chuyện:

1. **Một bàn làm việc** — hàng chờ · Gantt · panel · dải chân trên cùng một khung.
2. **Ba mức kiểm soát rành mạch** — chặn đặt lịch / chặn phát hành / cảnh báo (§7), mỗi vấn đề nói
   rõ nguyên nhân · nguồn dữ liệu · đối tượng ảnh hưởng · hành động sửa.
3. **Thời gian chạy theo thực tế xưởng** — đã bắt đầu thì chạy liên tục tới xong, không tách đoạn
   theo ca (§3).

Màn 2 **không** sao chép máy · tổ · ca · vật tư · LSX · bài ghép · lịch nghỉ. Mọi cửa phát hành —
kể cả bấm từ màn cũ — đi qua **cùng một gate v2** (§9.3), nên hai màn không thể lệch luật.

---

## 2. Nguồn dữ liệu — không đẻ bảng lịch mới

Toàn bộ luật dưới đây chạy được bằng dữ liệu ĐANG CÓ. Đợt này chỉ thêm **một migration quyền**.

| Luật cần | Nguồn thật (bảng.cột) |
| --- | --- |
| Dải tốc độ máy | `may_thiet_bi.toc_do` (TB) · `toc_do_min` · `toc_do_max` · `makeready_time_default` |
| Dải năng suất tổ | `cong_doan_dinh_muc.nang_suat_nguoi_gio(_min/_max)`, ghim vào bước qua `khoan_json` |
| Ba mức thời lượng | `lsx_service.thoi_luong_buoc()` — đã trả `chiem_may_phut` + `_min` + `_max` |
| Ca làm việc | `work_shifts` đang hoạt động (`is_active`), ca đêm theo `is_overnight` |
| Ngày nghỉ · ngày lễ | `work_calendar_config` + `special_days` (`kind` = off / off1x / work) |
| Số người của bước | `lsx_cong_doan.so_nhan_cong(_toi_thieu/_tieu_chuan/_toi_da)`, mirror ở `bai_ghep_cong_doan` |
| Quân số tổ theo ngày | `to_quan_so_ngay` (gõ đè + `ly_do` bắt buộc); không có dòng ⇒ tự tính từ `employees` − `leaves` đã duyệt |
| Vật tư giữ chỗ | `vat_tu_giu_cho` (`nguon` = kho / dang_ve, `ngay_ve`) + cờ `lsx.giu_cho_bat` · `bai_ghep.giu_cho_bat` |
| Hai hạn | `lsx.han_hoan_thanh_sx` · `lsx.han_giao_khach` · `bai_ghep.han_hoan_thanh_sx` |
| Lệnh gấp | `lsx.is_rush` · `bai_ghep.is_rush` |
| Máy hỏng · bảo trì | `machine_unavailable_periods` (`kieu` = chan / mo_them), chỉ ĐỌC từ module Kỹ thuật máy |
| Trạng thái xử lý vấn đề · ngoại lệ | `xep_lich_van_de` (`trang_thai`, `exception_ly_do/by/expires_at`) |
| Chống ghi đè | `xep_lich_cong_doan.updated_at` |
| Phát hành | `lsx.trang_thai` / `bai_ghep.trang_thai` = `da_phat_hanh` |

Không lưu thêm số dẫn xuất nào: thời lượng · sớm-nhất/muộn-nhất · độ dư · tải · nhãn vấn đề đều
**tính lúc đọc**, bám precedent `thoi_luong_buoc` / `tinh_so_to`.

---

## 3. Thời lượng và ca

- Thanh Gantt **chiếm lịch theo mức trung bình**; râu hai đầu vẽ mức nhanh nhất – chậm nhất.
- Máy chưa khai `toc_do_min`/`toc_do_max` ⇒ ba mức bằng nhau; UI phải nói "chưa khai dải", KHÔNG
  vẽ râu 0 như thể máy chạy chính xác tuyệt đối.
- **Giờ bắt đầu phải nằm trong một ca đã cấu hình.** Đây là cửa chặn duy nhất của ca.
- **Đã bắt đầu thì chạy liên tục tới xong**: `finish = start + chiem_may_phut` theo giờ tường,
  KHÔNG cắt theo khung ca, KHÔNG tách nhiều đoạn. Phần tràn qua cuối ca vẫn chiếm máy và vẫn ăn
  suất người của tổ.
- **Ngày nghỉ · ngày lễ vẫn có ca khả dụng như ngày thường** — chỉ tô nền khác + ghi chú tên ngày
  lễ lấy từ `special_days.name`. Đây là chỗ v2 khác hẳn màn cũ (màn cũ để trống ngày nghỉ).
- Việc kéo qua nửa đêm là bình thường, không phải lỗi.
- Xếp lịch 2 **không** quản lý tăng ca và phát sinh thực tế ngoài kế hoạch.

*Ví dụ số*: máy in TB 6.000 tờ/giờ (min 4.500 · max 7.500), chuẩn bị 45 phút, việc 30.000 tờ ⇒
thanh 5h45 (45 phút + 5h00), râu 4h45 – 7h25. Đặt 20:00 trong ca 2 (14:00–22:00) ⇒ kết thúc 01:45
hôm sau, vẫn chiếm máy suốt khoảng đó.

---

## 4. Nhân lực

- Mỗi công đoạn chiếm **đúng `so_nhan_cong`** đã lưu ở LSX/bài ghép. Màn 2 không sửa số người và
  không chọn nhân viên cụ thể.
- Hiện kèm tham khảo: kế hoạch · tối thiểu · tiêu chuẩn · tối đa. **Không** phán xét cao/thấp so
  với định biên.
- Quân số tổ khả dụng theo ngày: dòng gõ đè của `to_quan_so_ngay` nếu có (hiện kèm lý do), không
  thì số tự tính (nhân viên đang làm thuộc đúng tổ lá − nghỉ phép đã duyệt). **Ngày lễ không tự
  trừ quân số.**
- **Chặn**: tổng suất người của các công đoạn cùng tổ **chồng giờ** vượt quân số khả dụng của ngày.

---

## 5. Vật tư · hạn · chuỗi công đoạn

- Hàng chờ hiện **mọi** LSX/bài ghép cần lập lịch, chia hai rổ: *Có thể xếp* và *Bị chặn*.
- Cho tạo **lịch nháp** khi routing + thời lượng hợp lệ, dù vật tư chưa đủ.
- Có ngày hàng hứa về (`vat_tu_giu_cho.ngay_ve` của lô `dang_ve`) ⇒ **không được bắt đầu trước ca
  đầu tiên của ngày đó**.
- Chưa có ngày về ⇒ vẫn đặt nháp được, **không được phát hành**.
- Chỉ phát hành khi vật tư đã xác định và **giữ đủ 100%**.
- Tuân thủ DAG của LSX và bài ghép: bước sau không bắt đầu trước khi tiền nhiệm hoàn thành.
- Hiện **đồng thời** hạn hoàn thành SX và hạn giao khách. Hạn SX là đích chính; thiếu hạn SX mới
  dùng hạn giao khách; thiếu cả hai ⇒ chặn phát hành.
- Bài ghép: bước chung theo hạn của **bài**; các nhánh sau điểm toả giữ hạn riêng của từng LSX.

---

## 6. Máy · thuê ngoài · lane

- **Bỏ hẳn** mọi kết luận theo khổ · số màu · định lượng: không kiểm, không lọc, không xếp hạng,
  không cảnh báo. (`_may_fit.py` vẫn còn cho màn cũ, v2 không gọi.)
- **Chặn** trùng việc trên cùng máy và đè khoảng `chan` của máy (hỏng/bảo trì).
- Máy hỏng/bảo trì chỉ đọc; panel có liên kết sang module Kỹ thuật máy, không sửa tại Gantt.
- Ba cụm lane: **Máy** · **Tổ** · **Nhà cung cấp**. Cụm NCC gom theo `nha_cung_cap` đã chuẩn hoá
  (trim + gộp khoảng trắng + không phân biệt hoa/thường); trống ⇒ lane "Thuê ngoài — chưa rõ NCC".
- Công đoạn thuê ngoài: thanh từ mốc gửi dự kiến (`start_at`) đến nhận dự kiến (`finish_at`), tham
  gia DAG và hạn như mọi bước khác; không chiếm máy, không ăn suất người.

---

## 7. Ba mức kiểm soát

Mỗi vấn đề trả về: `muc` · `ma` · `cau` (câu người đọc) · `nguon` (bảng/cột hoặc module nguồn) ·
`anh_huong` (dòng/LSX/bài bị ảnh hưởng) · `sua` (hành động + đích mở).

**7.1 Chặn đặt lịch** (`chan_dat_lich`) — không cho lưu dòng:

| Mã | Nghĩa |
| --- | --- |
| `thieu_thoi_luong` | Không tính được thời lượng (chưa khai tốc độ/năng suất) |
| `thieu_quy_doi` | Thiếu cầu quy đổi đơn vị giữa SL vào và đơn vị tốc độ |
| `thieu_tai_nguyen` | Chưa có máy / tổ / NCC cần thiết |
| `ngoai_ca` | Giờ bắt đầu không nằm trong ca nào |
| `sai_tien_nhiem` | Bắt đầu trước khi bước tiền nhiệm hoàn thành |
| `truoc_ngay_vat_tu` | Bắt đầu trước ca đầu tiên của ngày vật tư hứa về |
| `trung_may` | Trùng việc khác trên cùng máy |
| `de_vung_khoa_may` | Đè khoảng máy hỏng/bảo trì |
| `vuot_quan_so_to` | Tổng suất người chồng giờ vượt quân số tổ trong ngày |

**7.2 Cho lưu nháp, chặn phát hành** (`chan_phat_hanh`):

| Mã | Nghĩa |
| --- | --- |
| `vat_tu_chua_du` | Chưa giữ đủ 100% |
| `vat_tu_chua_xac_dinh` | Còn dòng vật tư chưa chốt món |
| `vat_tu_chua_co_ngay` | Lô `dang_ve` không có `ngay_ve` |
| `con_buoc_chua_xep` | Còn công đoạn chưa có tài nguyên hoặc chưa có giờ |
| `thieu_ca_hai_han` | Thiếu cả hạn SX lẫn hạn giao khách |
| `tre_han_sx` | Hoàn thành sau hạn SX — **chỉ mã này** được duyệt ngoại lệ kèm lý do |

**7.3 Cảnh báo, không chặn** (`canh_bao`): `toi_da_lan_viec_ke` (mức chậm nhất lấn việc kế tiếp) ·
`sat_han_sx` · `dem_giao_ngan` (đệm SX→giao khách quá ngắn) · `vat_tu_dang_ve` · `tai_cao` (máy/tổ
tải cao) · `sap_bao_tri`.

---

## 8. Một bàn làm việc

Mặc định 14 ngày cuốn chiếu; zoom giờ · ca · ngày · tuần. Thanh trên: tìm kiếm + lọc máy · tổ ·
NCC · chưa xếp · có vấn đề · lệnh gấp. **Không** dựng lại ba màn Bảng/Gantt/Vấn đề rời.

- **Hàng chờ (trái)** — hạn SX · hạn giao · vật tư · số công đoạn chưa xếp · lý do bị chặn. Chọn
  một LSX/bài làm nổi cả chuỗi trên Gantt. Bước bị chặn xem được nhưng không kéo được. Hành động
  sửa mở đúng module nguồn.
- **Gantt (giữa)** — ba cụm lane; nền ca · ngày lễ · vùng máy hỏng · tải người của tổ. Chọn bước
  chưa xếp ⇒ tối đa **ba gợi ý**, ưu tiên tránh trễ/lệnh gấp trước, rồi mới gom giấy–khổ–bộ mực.
  Preview vẽ vị trí giả + nêu giờ kết thúc · công đoạn bị ảnh hưởng · hạn mới · vấn đề mới.
  **Preview không ghi dữ liệu**; chỉ xác nhận mới lưu.
- **Panel (phải)** — LSX/bài + vị trí trong DAG · hai hạn + đệm · ba mức thời lượng kèm nguồn tính
  · máy/tổ/NCC + ca + tải · số người kế hoạch và định biên tham khảo · quân số tổ và phần còn rảnh
  · vật tư đã giữ / đang về / còn thiếu + ngày sớm nhất · danh sách chặn-cảnh báo kèm liên kết xử lý.
- **Dải chân** — tổng số chặn đặt lịch · chặn phát hành · cảnh báo; bấm số làm nổi đúng thanh/LSX.
  Phát hành độc lập theo từng LSX hoặc bài ghép. Lịch đã phát hành bị khoá; sửa thì phải **thu hồi
  có quyền + lý do** rồi phát hành lại.

---

## 9. Backend và API v2

### 9.1 Tách tầng

`services/xep_lich_2/` — `context.py` (read-model) · `constraint.py` (ba mức) · `suggestion.py`
(gợi ý + preview) · `release.py` (gate phát hành/thu hồi) · `service.py` (facade). Truy vấn mới
nằm trong `repositories/xep_lich_2_repo.py`; router chỉ kiểm quyền và điều phối.

### 9.2 Endpoint (`/api/xep-lich-2`, module quyền `xep_lich_2`)

| Method + path | Việc |
| --- | --- |
| `GET /workspace` | lane · ca · ngày lễ · quân số · tải · thanh trong cửa sổ đang xem |
| `GET /queue` | hàng chờ, phân trang, chia *có thể xếp* / *bị chặn* |
| `GET /context/{nguon}/{id}` | chuỗi DAG + dữ liệu panel |
| `POST /entities/{nguon}/{id}/draft` | sinh lịch nháp, khoá routing |
| `DELETE /entities/{nguon}/{id}/draft` | gỡ lịch nháp chưa phát hành |
| `POST /rows/{id}/suggestions` | tối đa ba khe |
| `POST /rows/{id}/preview` | mô phỏng, KHÔNG ghi |
| `PUT /rows/{id}` | lưu, kèm `expected_updated_at` |
| `POST /{nguon}/{id}/release` · `POST /{nguon}/{id}/recall` | phát hành · thu hồi (có lý do) |

`nguon` ∈ `lsx` | `bai_ghep`. Dữ liệu đã đổi từ lúc đọc ⇒ **409** kèm giá trị mới, không ghi đè.
Mọi mutation `hub.broadcast({"type": "xep_lich_changed"})` (+ `lsx_changed` / `bai_ghep_changed`),
FE nghe qua `connectQuoteEvents` — badge · hàng chờ · cửa phát hành tự nhảy, không cần refresh.

### 9.3 Gate phát hành dùng chung

`release.py` là **nơi duy nhất** quyết định được-phát-hành-hay-không. Router màn cũ gọi vào đây
thay cho nhánh riêng của nó, nên phát hành từ màn cũ không vượt được luật v2.

### 9.4 Migration

`0218_xep_lich_2`: chép quyền `xep_lich` → `xep_lich_2` (kèm hai bit `approve` và
`approve_exception`), thêm khoá vào ma trận, đếm chốt chặn như mg 0216. **Không** bảng/cột lịch mới.

---

## 10. Quyết định chốt 18/08/2026

1. **Ngày lễ** đọc `special_days` của module Nhân sự — không đẻ bảng lịch lễ riêng. v2 vẫn cho xếp
   ngày lễ (khác `is_working_day` của màn cũ), chỉ tô nền + ghi chú.
2. **Chạy liên tục qua cuối ca**: ca chỉ gác *giờ bắt đầu*; nền ca thành nền hiển thị chứ không
   còn cắt thời lượng.
3. **Lane NCC** gom theo chuỗi `nha_cung_cap` đã chuẩn hoá (chưa có danh mục NCC cho thuê ngoài).
4. **Trạng thái vấn đề dùng chung** `issue_key` với màn cũ — cùng một lịch thật thì cùng một vết
   xử lý; đã tiếp nhận/duyệt ngoại lệ ở màn cũ thì màn 2 thấy luôn.
5. **Gate phát hành** tách thành module dùng chung ngay từ đợt này (§9.3).

---

## 11. Không làm trong đợt này

- **Không** build schema thực tế sản xuất. Contract tương lai: baseline kế hoạch giữ nguyên; module
  sản xuất sở hữu giờ chạy thực tế; Gantt sau này đọc lớp phủ thực tế và chỉ cho lập lại phần lịch
  **chưa chạy**.
- **Không** hợp nhất quyền, **không** đổi route/menu quen thuộc, **không** gỡ UI cũ — chỉ sau khi
  pilot bằng quyền `xep_lich_2` trên lịch thật và được nghiệm thu.
- **Không** reset/checkout/commit/push các thay đổi đang có.

---

## 12. Kịch bản kiểm thử bắt buộc

1. Bắt đầu trong ca, kết thúc sau cuối ca (không tách đoạn).
2. Ngày lễ vẫn xếp được như ngày thường (nền lễ + ghi chú).
3. Máy hỏng nằm giữa khoảng chạy ⇒ chặn.
4. Ba việc cùng tổ chồng nhau làm vượt quân số ⇒ chặn.
5. Công đoạn kéo qua nửa đêm.
6. Vật tư: đang về · không có ngày về · chưa giữ đủ · đã giữ đủ.
7. LSX thường · lệnh gấp · bài ghép nhiều nhánh · công đoạn thuê ngoài.
8. Không còn kết luận nào dựa trên khổ / số màu / định lượng.
9. Hai người sửa cùng một dòng ⇒ 409.
10. Phát hành từ màn cũ không vượt được gate v2.
11. SSE cập nhật lịch · hàng chờ · badge · cửa phát hành mà không cần refresh.
