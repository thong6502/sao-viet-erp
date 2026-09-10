# SPEC — XẾP LỊCH 3 (cấp LỆNH SẢN XUẤT)

> Module **MỚI**, dựng song song. `xep_lich_2` bị **ẩn đường vào** bằng cờ ở
> `frontend/src/constants/features.ts` — đúng cách Bài ghép đã ẩn — **không gỡ code, không drop bảng**
> trong đợt này. Anh em: `spec-xep-lich-2.md` (màn bị thay), `spec-thuc-hien-san-xuat.md` (nơi nhận
> phát hành), `spec-cong-doan.md`.

---

## 1. Mục tiêu duy nhất

**Người chọn thời điểm bắt đầu của một LỆNH SẢN XUẤT → hệ trả ngày kết thúc của LỆNH đó.**

Hết. Không có mục tiêu thứ hai.

Thời lượng chạy của từng công đoạn đã biết sẵn (engine `lsx_service.thoi_luong_buoc`), nên ngày kết
thúc không phải phỏng đoán: cộng dồn thời lượng các bước rồi cộng thêm các bữa nghỉ giữa ca và các
khoảng ngoài giờ ca mà nó vắt qua.

**NGOÀI phạm vi — cố ý bỏ, không phải nợ:** gán máy · gán tổ · chống trùng máy · cân quân số tổ ·
tách/gộp lần chạy · danh sách vấn đề · gate chặn phát hành · tự-xếp · gợi ý khe · bài ghép (module
đã ẩn). Người dùng **không bấm** thứ nào trong số đó.

**KHÔNG CHẶN GÌ HẾT** là quyết định chốt (10/09/2026). Thiếu vật tư, trễ hạn, chồng chéo — hiện màu
để nhìn thấy, rồi vẫn cho đi tiếp. Người quyết, máy chỉ ghi nhận.

---

## 2. Chỉ lưu MỘT con số

Bảng mới `xep_lich_lenh`, **một dòng một lệnh**:

| Cột | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id` | Integer PK | |
| `lsx_id` | Integer, **UNIQUE**, FK `lsx.id` ON DELETE CASCADE | một lệnh chỉ có một mốc |
| `bat_dau_at` | DateTime(tz) NOT NULL | **thứ duy nhất người quyết** |
| `created_by` | Integer | → `users.id` |
| `created_at` / `updated_at` | DateTime(tz) | `updated_at` là chốt chống ghi đè khi hai người cùng kéo |

Không có cột nào khác. Đặc biệt **không lưu** `ket_thuc_at`, không lưu mốc từng bước, không lưu máy,
không lưu trạng thái dòng. Mọi thứ đó **tính lúc đọc** — bám precedent `thoi_luong_buoc` /
`tinh_so_to` của repo.

Lý do không lưu ngày kết thúc: nó phụ thuộc ca làm việc, ngày nghỉ, tốc độ máy và số lượng — bốn thứ
đổi được sau lưng. Lưu ra là ngày kết thúc chết cứng trong khi cấu hình đã khác, mà số trông-như-thật
thì không ai đi kiểm.

---

## 3. Công thức

```
con trỏ = bat_dau_at
với mỗi bước theo THU_TU tăng dần:
    bước_bắt_đầu = con trỏ
    bước_kết_thúc = _cong_gio_lam(con trỏ, thời_lượng_bước, LichXuong)
    con trỏ = bước_kết_thúc
ngày_kết_thúc_lệnh = con trỏ
```

Ba mảnh đều **có sẵn, không viết mới**:

- **Thời lượng bước** — `lsx_service.thoi_luong_buoc(cd, may=…, sl_tinh=…)`, lấy `chiem_may_phut`
  (mức trung bình). Máy để tính tốc độ lấy từ `lsx_cong_doan.may_id` — cột này đã được chép sẵn từ
  danh mục lúc tạo lệnh, **nên không cần ai gán máy ở bàn xếp lịch**.
- **Khung giờ làm** — `xep_lich_service.LichXuong`, dựng từ `work_shifts` đang hoạt động có
  `ca_san_xuat = true`, chồng lịch nghỉ `CalendarService` (`work_calendar_config` + `special_days`),
  khoét bữa nghỉ từ `work_shifts.break_start_minute/break_end_minute`.
- **Phép cộng** — `xep_lich_service._cong_gio_lam(bắt_đầu, phút, lich)`: cộng đúng số phút CHẠY, tự
  nhảy qua bữa cơm, qua khoảng ngoài ca, qua ngày nghỉ. Ca đêm vắt nửa đêm đã xử lý sẵn.

Dùng khung **theo ca** (`lien_tuc=False`), khác hẳn màn 2 vốn cho máy chạy trọn ngày. Đây chính là
chỗ "cộng thêm thời gian ngoài ca" mà mục tiêu đòi.

**Chuỗi bước bám `thu_tu`, KHÔNG bám `phu_thuoc`** — giữ đúng quy ước đang chạy của repo (xem
`routing-dag-thoi-luong`): bước sau nối đuôi bước trước, không có nhánh song song.

### 3.1 Ví dụ số

Lệnh 30.000 tờ, routing 3 bước: In 5h45 · Cán 2h00 · Bế 3h00 ⇒ **10h45 giờ chạy**.
Xưởng bật một ca sản xuất: Ca 1 06:00–14:00, nghỉ cơm 11:00–12:00. Thứ Bảy · Chủ nhật nghỉ.
Người thả thanh vào **thứ Sáu 11/09 lúc 08:00**:

| Chặng | Diễn biến |
| --- | --- |
| 08:00 → 11:00 | chạy 3h00 (In còn 2h45) |
| 11:00 → 12:00 | **nghỉ cơm**, cộng vào thanh, không tính giờ chạy |
| 12:00 → 14:00 | chạy 2h00 (In còn 45') |
| 14:00 → 06:00 T2 | **ngoài ca + hai ngày nghỉ**, cộng vào thanh |
| T2 14/09 06:00 → 06:45 | In hết 45' còn lại, **xong 06:45** |
| 06:45 → 08:45 | Cán 2h00, **xong 08:45** |
| 08:45 → 11:00, nghỉ, 12:00 → 12:45 | Bế 3h00 (2h15 + 45'), **xong 12:45** |

⇒ Thanh trải **11/09 08:00 → 14/09 12:45**, trong đó 10h45 là giờ chạy thật.

Kiểm chéo bằng năng lực ngày: ca này cho 420 phút chạy/ngày. Thứ Sáu tính từ 08:00 chỉ còn 300
phút; 345 phút còn lại rơi sang thứ Hai (300 phút buổi sáng + 45 phút sau bữa cơm) ⇒ 12:45.
*(Bảng này từng ghi "xong 15/09 07:45" — sai số học: nó cho Cán chiếm 06:45→12:45 tức 5 tiếng thay
vì 2 tiếng. Sửa 10/09/2026, trước khi con số bị khoá vào test.)*

*Lưu ý cấu hình:* seed hiện bật cả Ca 1 · Ca 2 · Ca 3 (06–14 · 14–22 · 22–06), tức khung phủ 24/24
và phần "ngoài ca" gần như bằng 0 — lúc đó thanh gần bằng đúng tổng giờ chạy. **Đó là đúng, không
phải lỗi**: xưởng khai chạy ba ca thì lệnh chạy liền mạch.

### 3.2 Mốc bắt đầu rơi vào chỗ không chạy được

Thả vào giữa bữa cơm, ngoài giờ ca, hay ngày nghỉ ⇒ mốc **tự trượt tới đầu khoảng chạy được gần
nhất** (`_vao_gio_lam`) và UI nói rõ *"đã dời sang 06:00 ngày 14/09"*. Đây là **làm tròn cho phép
cộng có nghĩa, không phải cửa chặn** — không có thông báo lỗi, không có nút xác nhận.

### 3.3 Bước thuê ngoài

Bước `loai_buoc = thue_ngoai` có thời lượng máy = 0. Nó chiếm khoảng bằng
`ngay_nhan_dk − ngay_gui_dk` tính theo **ngày lịch** (không trừ ca, không trừ ngày nghỉ — nhà cung
cấp chạy theo lịch của họ). Thiếu một trong hai ngày ⇒ chiếm 0 và thanh mang **chú thích** *"chưa
khai ngày gia công ngoài, lệnh có thể kết thúc muộn hơn"*. Không chặn.

---

## 4. Mốc từng công đoạn — số THỪA, không phải tính năng

Để ra được ngày kết thúc của lệnh, phép cộng bắt buộc đi qua từng bước, nên mốc bắt đầu/kết thúc của
từng công đoạn tự rơi ra. Chúng được **trả kèm** trong API, **không lưu**, **không giữ chỗ máy**,
**không chặn ai**, và **người dùng không sửa được**.

Chúng phục vụ đúng ba chỗ đang cần: bàn tổ ở Thực hiện SX, "ngày cần" của kế hoạch vật tư, và cột
"máy đang chạy" ở màn Thiết bị (§7).

**Màn xếp lịch KHÔNG bày mốc bắt đầu/kết thúc của từng công đoạn** (chốt 10/09/2026 trên bản phác
thảo): bảng công đoạn chỉ có tên bước · máy/tổ · số lượng vào · kíp chuẩn · giờ chạy, cộng dòng
tổng. Mốc từng bước chỉ tồn tại trong API cho ba chỗ trên, không hiện cho người xếp lịch — họ chỉ
cần hai mốc của cả lệnh.

### 4.1 Chi phí tính lại — ranh giới rõ

Trải lịch một lệnh là vài chục phép cộng, nhưng **bốn chỗ ở §7 đều hỏi cho NHIỀU lệnh cùng lúc**, nên:

- `LichXuong` dựng **một lần cho mỗi request** rồi dùng lại cho mọi lệnh — đừng dựng trong vòng lặp
  (mỗi lần dựng là một lượt đọc `work_shifts` + lịch nghỉ).
- Mọi đường đọc phải **cắt theo cửa sổ thời gian hoặc theo tập `lsx_id`**, không có đường nào trải
  toàn bộ lịch sử. `GET /lich` bắt buộc có `tu`/`den`.
- Nạp bước routing của cả lô lệnh bằng **một truy vấn** (`lsx_cong_doan.lsx_id IN …`), không N+1.

Đo trước/sau bằng số lệnh thật khi làm; thấy chậm thì sửa ngay tại chỗ.

---

## 5. Màn hình

Bố cục chốt 10/09/2026 theo bản phác thảo đã nghiệm: **bộ lái cửa sổ · hàng chờ bên trái · Gantt bên
phải · panel chi tiết bên dưới**. Không có panel thứ tư, không có tab.

**Đầu màn — bộ lái cửa sổ, hai trục.** (1) **Độ dài** cửa sổ: `[Tuần][2 tuần][Tháng]` = 7 / 14 / 30
ngày, đổi mức thì **giữ tâm** cửa sổ. (2) **Vị trí** cửa sổ: `‹ N ngày` · ô chọn ngày
(`input[type=date]`, trỏ ngày ĐẦU cửa sổ) · `N ngày ›` · nút tròn **Hôm nay**; hai mũi tên nhảy
**trọn một cửa sổ**, không nhảy từng ngày. Nhãn hai nút đổi theo mức đang chọn.

**Dải số liệu — VĂN XUÔI, một hàng, hết bề ngang** (chốt theo bản người dùng duyệt 10/09/2026, KHÔNG
nén thành chuỗi chữ hoa): số lệnh trong cửa sổ · số chờ xếp · khoảng cửa sổ (`10/09→16/09`) · tổng
giờ chạy **rơi trong cửa sổ** · số lệnh trễ hạn SX · khung ca sản xuất và giờ nghỉ đang áp dụng.
Dòng cuối giải thích mọi khoảng nhạt trên thanh nên phải hiện ngay đầu màn, không giấu vào chú giải
hay cấu hình. "Giờ chạy trong cửa sổ" tính bằng phần đoạn chạy **giao với** cửa sổ — lệnh vắt qua
mép chỉ được tính phần thật sự nằm trong khoảng đang xem.

**Trái — hàng chờ.** Thẻ lệnh `san_sang` chưa có mốc: mã · tên · **khách hàng** · hạn SX · tổng giờ
chạy · số tờ in. Lệnh gấp đổi màu vạch bên trái thẻ. Tìm theo mã/tên, **phân trang + lọc ở MÁY CHỦ**
(bắt buộc, xem `phan-trang-loc-o-may-chu`).

**Phải — Gantt theo LỆNH.** Trục ngang là cửa sổ đang mở (7 / 14 / 30 ngày), trục dọc là **lệnh**,
mỗi lệnh **một hàng một thanh**, xếp theo mốc bắt đầu tăng dần — thứ tự **đóng băng trong lúc kéo**,
nhả chuột mới sắp lại (hàng nhảy dưới con trỏ là mất phương hướng). **Chỉ hiện lệnh CHẠM cửa sổ**
(máy chủ đã lọc theo `tu`/`den`); riêng lệnh đang bị kéo thì luôn giữ hàng, kể cả khi vừa bị đẩy ra
ngoài mép. Không có lane máy, không có lane tổ.

- Nhãn hàng (264px, bốn dòng): (1) mã lệnh + nhãn "gấp" nếu `is_rush`, **canh phải là máy chính**
  (`may_ten`, mono chữ hoa nhỏ); (2) tên sản phẩm + tình trạng vật tư trong ngoặc — `(đủ)` /
  `(thiếu VT)` / `(chưa giữ)`; (3) khách hàng, **canh phải là chip `TRỄ HẠN`** khi mốc kết thúc vượt
  `han_hoan_thanh_sx`; (4) sản lượng · số tờ in · con/tờ.
- **Thanh hai lớp**: nền nhạt là toàn bộ khoảng lệnh chiếm chỗ; các khối đậm bên trong là những đoạn
  máy **thực sự chạy trong ca**, mỗi công đoạn một sắc độ đậm dần theo thứ tự và khớp ô màu ở bảng
  dưới. Khoảng cách giữa hai lớp chính là phần nghỉ giữa ca, ngoài ca và ngày nghỉ — đây là thứ
  người xếp lịch cần thấy, không phải một hộp trơn.
- **Lệnh chạy ra ngoài cửa sổ**: thanh bị cắt ở mép, mép cắt bỏ bo góc và hiện mũi tên `‹` (bắt đầu
  trước cửa sổ) hoặc `›` (còn chạy sau cửa sổ).
- Nhãn `xong <mốc>` đặt **bên phải** thanh (không đặt trong thanh, không đặt phía trên — chồng vạch
  hạn), và **chỉ vẽ khi mốc kết thúc nằm TRONG cửa sổ** — nhãn dính mép phải là nhãn nói sai. Lệnh
  trễ hạn: nhãn thành `⚠ trễ hạn · xong <mốc>`, màu `--signal`.
- **Kéo từ hàng chờ thả vào Gantt** = đặt mốc lần đầu; **kéo ngang thanh** = dời mốc, bám **15 phút**
  một nấc, nhả ra là các khối chạy tự cắt lại theo ca mới. Kéo **hai mép** không làm gì (độ dài là số
  dẫn xuất). Rơi ngoài giờ chạy ⇒ tự dời + băng thông báo nói rõ dời đi đâu (§3.2).
- **Cửa sổ càng rộng, nấc kéo càng thô**: Tuần ≈ 110px/ngày (15 phút ≈ 1,1px), 2 tuần ≈ 72px
  (0,75px), Tháng ≈ 40px (0,4px). Kéo chuột chốt được NGÀY và giờ thô; chốt tới nấc 15 phút phải qua
  bàn phím (◀▶ = 15 phút, Shift+◀▶ = một ca) hoặc ô giờ ở panel chi tiết. Đây là cái giá của cửa sổ
  rộng, chấp nhận được vì mục tiêu của màn là **ngày** kết thúc.
- **Ba lớp báo trễ hạn, không lớp nào chỉ dựa vào màu**: chip `TRỄ HẠN` ở nhãn hàng · `⚠` + chữ
  "trễ hạn" ở nhãn cuối thanh · nền thanh và khối chạy đổi sang họ `--signal`. Chữ "trễ hạn" **không**
  đặt trong lòng thanh như bản tham chiếu, vì thanh của ta có khối chạy bên trong — chữ sẽ đè số liệu.
- **Hai vạch hạn** trên mỗi hàng: nét **đứt** = hạn hoàn thành SX, nét **chấm** nhạt = hạn giao khách;
  vạch nằm ngoài cửa sổ thì không vẽ. Nhìn được khoảng đệm còn lại giữa hai mốc. Chỉ báo, không chặn.
- Nền tô khác cho ngày nghỉ/lễ **cả ở hàng tiêu đề và trong rãnh** (hai lớp phải khớp cột), tên ngày
  lễ lấy từ `special_days.name`. Ô ngày **hôm nay** đổi màu số + dấu chấm `--rust` cạnh tên thứ.
- Chú giải ở chân: máy chạy trong ca · nghỉ và ngoài ca · hạn hoàn thành SX · trễ hạn SX · ý nghĩa
  `‹ ›`.

**Dưới — panel chi tiết của lệnh đang chọn.** Đúng mười hai ô, không hơn (chốt trên phác thảo):
khách hàng · đơn + PO khách · người kinh doanh · sản lượng (kèm số tờ in, con/tờ) · giấy + khổ in ·
màu + số kẽm · hạn hoàn thành SX · hạn giao khách · phụ trách kế hoạch · lịch (bắt đầu → kết thúc) ·
giờ chạy (kèm giờ nghỉ và ngoài ca) · kíp chuẩn cả lệnh. Trên cùng là chip **lệnh gấp** ·
**trong hạn / trễ hạn SX** · **tình trạng giữ chỗ vật tư**, và nút **Phát hành xuống xưởng** — bấm là
đi, không hỏi lại, không kiểm gì. Có `luu_y_gui_xuong` thì bày thành băng riêng.

Bảng công đoạn: tên bước · máy/tổ · số lượng vào · kíp chuẩn · giờ chạy + dòng tổng. **Không có cột
mốc bắt đầu/kết thúc** (§4).

**Không bày** (đã cân nhắc và bỏ): chừa tách chiều, số lượt chạy, lead time, tổng tiền khoán dự
kiến, ghi chú nội bộ của lệnh, danh sách `thieu`.

Tái dùng cơ chế kéo-thả pointer đã có ở `Xl2Gantt.tsx` (`DragState` + `pointermove/up/cancel`), viết
lại cho đơn vị "một hàng một lệnh" — **không sửa file cũ**, module 3 có file riêng.

**Bẫy đã dính khi phác thảo, đừng lặp:** hàng lưới khai `grid-template-columns` đủ N cột ngày nhưng
chỉ đặt hai ô con (nhãn + dải) ⇒ dải thời gian bị nhét vào bề rộng đúng một ngày và mọi thanh trông
mảnh như que. Hàng chỉ có **hai** cột (`264px minmax(0,1fr)`); lưới N ngày nằm **bên trong** dải, và
`min-width` của khung phải ≥ tổng bề rộng tối thiểu của hàng tiêu đề — **đặt lại mỗi lần đổi mức thu
phóng** (1034 / 1272 / 1464px, xem `design-xep-lich-3-ui.md` §3) để hai lớp không lệch nhau.

---

## 6. API — `/api/xep-lich-3`, module quyền `xep_lich_3`

| Method | Đường dẫn | Việc |
| --- | --- | --- |
| GET | `/hang-cho` | lệnh chưa có mốc (`trang`, `moi_trang`, `q`) — phân trang ở máy chủ |
| GET | `/lich?tu=&den=` | các lệnh có mốc chạm cửa sổ + thanh + chuỗi bước dẫn xuất |
| GET | `/lenh/{lsx_id}` | chi tiết một lệnh: chuỗi bước, mốc, chú thích |
| PUT | `/lenh/{lsx_id}` | đặt/dời mốc `{bat_dau_at, expected_updated_at}` → trả mốc đã làm tròn + ngày kết thúc mới |
| DELETE | `/lenh/{lsx_id}` | gỡ khỏi lịch → lệnh về `san_sang`, routing sửa lại được |
| POST | `/phat-hanh/{lsx_id}` | phát hành xuống xưởng — **không gate** |
| DELETE | `/phat-hanh/{lsx_id}` | thu hồi phát hành |

`PUT` không có `expected_updated_at` khớp ⇒ 409 kèm bản mới nhất (chống hai người cùng kéo đè nhau).

**Vòng đời lệnh giữ nguyên:** `san_sang` → (đặt mốc) `da_lap_ke_hoach` — routing khoá →
(phát hành) `da_phat_hanh`. Gỡ mốc thì lùi về `san_sang` và mở lại routing.

Phát hành và thu hồi **đẩy SSE** như đường hiện hành (nguyên tắc real-time nội bộ của repo).

---

## 7. Nối lại bốn chỗ đang đọc bảng lịch cũ

Cả bốn theo cùng một luật: **có dòng `xep_lich_lenh` thì đọc mốc dẫn xuất của module 3; không có thì
giữ nguyên đường cũ.** Chỉ THÊM nhánh, không sửa hành vi cũ.

1. **Phát hành → bàn tổ** (`san_xuat/snapshot.py:271`): `CongViec.du_kien_bat_dau/ket_thuc` lấy mốc
   dẫn xuất của bước; `may_id` lấy từ `lsx_cong_doan.may_id`.
2. **Giữ chỗ vật tư** (`giu_cho_repo.da_len_lich`): hợp thêm tập `lsx_id` của bảng mới.
3. **Kế hoạch vật tư** (`ke_hoach_vat_tu_repo.dong_lich_da_xep`): "ngày cần" = mốc bắt đầu của bước
   dẫn xuất.
4. **Cột máy đang chạy** ở màn Thiết bị (`may_trang_thai.lenh_dang_chay`): quét mốc dẫn xuất, khớp
   `may_id` của bước với giờ hiện tại.

---

## 8. Ẩn module 2

Thêm cờ `XEP_LICH_2_ENABLED = false` vào `frontend/src/constants/features.ts` và bọc mục nav
`xep-lich-cong-doan-2` trong `Sidebar.tsx` y hệt cách `BAI_GHEP_ENABLED` đang bọc Bài ghép — mất mục
menu là AppShell khoá luôn route. Backend `xep_lich_2` **vẫn mount, vẫn chạy test**; bảng
`xep_lich_cong_doan` / `xep_lich_van_de` **giữ nguyên dữ liệu**.

Bật lại chỉ là đổi một chữ.

---

## 9. Migration

Không có Alembic — mọi thứ viết vào `backend/app/db_migrations.py`:

1. Tạo bảng `xep_lich_lenh` (create_all không ALTER được, prod cần migration thật).
2. Thêm ô quyền `xep_lich_3`, **chép từ vai nào đang có `xep_lich_2`** (theo lối mg `0218` đã chép
   `xep_lich` → `xep_lich_2`) để không ai mất quyền.
3. Cập nhật `docs/DB_SCHEMA.md` **cùng lượt** — có guard test, thiếu là `init` đỏ.

Không cột Boolean nào trong bảng mới, nên không dính bẫy `server_default="0"`.

---

## 10. Không làm trong đợt này

- Không gỡ `xep_lich_2` (BE, FE, test, bảng) — chỉ ẩn đường vào.
- Không đụng bài ghép (module đã ẩn); `xep_lich_lenh` **không có** `bai_ghep_id`.
- Không nhánh song song trong routing (bám `thu_tu`).
- Không tăng ca, không phát sinh thực tế — thuộc Thực hiện SX.
- Không tự-xếp hàng loạt, không gợi ý khe trống, không xếp ngược từ hạn.

---

## 11. Kịch bản kiểm thử bắt buộc

**Backend**

1. Lệnh 3 bước, một ca 06:00–14:00 nghỉ 11:00–12:00, bắt đầu thứ Sáu 08:00 ⇒ kết thúc đúng §3.1.
2. Bật cả ba ca ⇒ thanh bằng đúng tổng giờ chạy (không cộng ngoài ca).
3. Mốc thả vào 11:30 (giữa bữa cơm) ⇒ trượt về 12:00, API trả cờ "đã dời".
4. Mốc thả vào Chủ nhật ⇒ trượt sang đầu ca thứ Hai.
5. Bước thuê ngoài khai gửi 11/09 nhận 15/09 ⇒ chiếm đúng 4 ngày lịch; thiếu ngày ⇒ chiếm 0 + chú thích.
6. Hai `PUT` cùng `expected_updated_at` cũ ⇒ cái sau 409.
7. Đặt mốc ⇒ lệnh sang `da_lap_ke_hoach`, `PUT /routing` bị khoá; gỡ mốc ⇒ về `san_sang`, mở lại.
8. Phát hành ⇒ `CongViec` nhận đúng mốc dẫn xuất và `may_id` của bước.
9. Lệnh chưa khai máy ở bước ⇒ thời lượng 0 + chú thích, **không** 500.

**Dev-browser — luồng UI thật, không dùng API thay bất kỳ bước nào**

Mở màn Xếp lịch 3 → kéo một lệnh từ hàng chờ thả vào Gantt → đọc ngày kết thúc hiện trên thanh →
kéo thanh sang thứ Bảy, thấy thanh dài ra và ngày kết thúc đổi → bấm thanh, đối chiếu chuỗi công
đoạn → bấm Phát hành → mở màn Thực hiện sản xuất, xác nhận bàn tổ thấy đúng việc với đúng giờ.
