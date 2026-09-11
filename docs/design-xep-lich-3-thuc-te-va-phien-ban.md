# Thiết kế — Xếp lịch 3: thực tế, dự kiến động, lịch sử phiên bản

> Nguồn: rà soát 10/09/2026, từ bốn câu hỏi của chủ dự án đặt trên panel lệnh `LSX26-0003`
> (gói `GPH26-0001`, phiên bản 8). Đây là spec **THIẾT KẾ — code chưa làm**. Mọi con số hiện trạng
> dưới đây đã kiểm bằng code và bằng truy vấn đọc DB dev, có dẫn nguồn.
>
> Đọc kèm: `docs/spec-xep-lich-3.md` (§1 không chặn, §4 mốc từng bước), `docs/design-xep-lich-3-ui.md`,
> `docs/spec-thuc-te-vs-ke-hoach.md` (§2.1 lớp thực tế CHỈ ĐỌC, §3 không tự dời lịch).

---

## 0. Năm việc — cái nào tốn schema, cái nào không

| # | Việc | Dữ liệu đã có? | Đụng schema? |
| --- | --- | --- | --- |
| 1 | Bày trạng thái + giờ KH/TT của **từng công đoạn** trong panel | Đủ | Không |
| 2 | "Dự kiến xong" **neo lại theo thực tế** (xong sớm → giảm, trễ → tăng) | Đủ | Không |
| 3 | Mốc = **bắt đầu phần còn lại** + **sàn không lùi** dưới bước đã xong | Đủ | Không |
| 4 | **Xem + so sánh** các phiên bản phát hành | **Đang bị ghi đè — mất** | **Có** (1 bảng) |
| 5 | Cột "Kế hoạch" ở Hồ sơ lệnh **lệch +7 giờ** | — (lỗi thật) | Không |

Việc 1–3 đi chung một đợt (cùng đụng `ChiTietOut` / `dat_moc` / `trai_lich`). Việc 4 tách riêng vì
có migration. Việc 5 vá độc lập, không chờ ai.

---

## 1. Hiện trạng — đã kiểm

### 1.1 Panel màn 3 chỉ có kế hoạch, cố ý

`CongDoanOut` (`backend/app/schemas/xep_lich_3.py:85`) ghi thẳng trong docstring: *"Dòng bảng công
đoạn trong panel. CỐ Ý không có mốc bắt đầu/kết thúc (spec §4)."* Danh sách bước ở
`frontend/src/pages/Xl3ChiTiet.tsx:376` vì vậy chỉ vẽ: tên · nhãn "song song được" · máy · số lượng
vào · số người · giờ chạy.

`docs/spec-xep-lich-3.md` §4 chốt ngày 10/09/2026: *"Màn xếp lịch KHÔNG bày mốc bắt đầu/kết thúc
của từng công đoạn"*, lý do là **người xếp lịch chỉ cần hai mốc của cả lệnh**.

Lý do đó đúng cho lệnh **chưa phát hành**. Lệnh **đã phát hành** thì panel không còn là bàn xếp
lịch nữa — nó là chỗ người điều độ nhìn xưởng. Chính panel đã đi nửa bước theo hướng đó rồi: cột
máy hiện `Máy cắt tờ Kyodo 132 ≠ KH Máy cắt tờ ITO 100`, tức `may_nguon="thuc_thi"` — nó **đã đọc
lớp thực thi** để nói máy thật khác máy kế hoạch. Thiếu đúng phần giờ và trạng thái.

### 1.2 "Dự kiến xong" mù trước thực tế

`XepLich3Service` tính kết thúc bằng `trai_lich(_naive(m.bat_dau_at), buoc, self._khung())`
(`backend/app/services/xep_lich_3/service.py:308` và `:327`). Ba đầu vào: mốc × routing × khung ca.
**Không đầu vào nào là thực tế.** Ghi kẽm chạy xong sớm 4 tiếng hay trễ 2 ngày, con số "Dự kiến
xong" vẫn y nguyên.

Số thực tế thì có đủ, nằm sẵn:

| Cần | Ở đâu |
| --- | --- |
| Trạng thái bước | `san_xuat_cong_viec.trang_thai` (`released`/`running`/`paused`/`completed`) |
| Bước xong lúc nào | `san_xuat_cong_viec.hoan_thanh_luc` (đóng dấu MỘT LẦN ở `thuc_thi.ket_thuc`) |
| Giờ chạy thật | `san_xuat_phien_chay.bat_dau` / `.ket_thuc` |
| Trễ có lý do | `san_xuat_phien_chay.ly_do_bat_dau_tre`, cờ `ket_thuc_tre` |
| Cam kết đã đẩy xuống xưởng | `san_xuat_cong_viec.du_kien_bat_dau` / `.du_kien_ket_thuc` |

`docs/spec-thuc-te-vs-ke-hoach.md` §1.1 đã ghi đúng lỗ này từ 31/08/2026 cho màn 2, chưa ai cài.

### 1.3 Mốc trải lại CẢ routing, kể cả bước đã xong

`dat_moc` (`service.py:390-430`) trải `buoc` = **toàn bộ** routing từ mốc; nó không biết bước nào đã
chạy, và không có chốt chặn nào (spec §1 của màn này là *"KHÔNG CHẶN GÌ HẾT"*).

Hệ quả quan sát được trên `LSX26-0003`: **Cắt tờ có kế hoạch 8/9, trong khi Ghi kẽm CTP — bước ngay
trước nó — hoàn thành 9/9 14:16.** Kế hoạch của bước sau nằm trước quá khứ của bước trước. Người
dùng không có cách nào để đặt mốc mà vẫn giữ được phần đã chạy.

### 1.4 Phiên bản: giữ được vỏ, mất ruột

`phat_hanh_cap_nhat` **sửa đè tại chỗ** rồi nâng số phiên bản
(`backend/app/services/san_xuat/release_update.py:267-269`):

```python
cv.du_kien_bat_dau = start
cv.du_kien_ket_thuc = finish
cv.phien_ban_so = new_ver
```

Đọc DB dev (gói `GPH26-0001`):

- `san_xuat_phien_ban`: **8 dòng** (v1 phát hành, v2…v8 cập nhật, mỗi dòng đủ `ly_do` + người + giờ).
- `san_xuat_cong_viec`: chỉ còn `phien_ban_so ∈ {1, 8}` — 3 dòng ở v1 (1 việc đã chạy + 2 việc lệch
  lần chạy), 6 dòng ở v8. **Nội dung v2…v7 không còn tồn tại.**

Nghĩa là hệ giữ được *ai đổi, lúc nào, vì sao* nhưng không giữ được *đổi cái gì*. Không có gì để
diff, nên không phải chuyện thiếu màn — thiếu dữ liệu.

Docstring của `SanXuatCongViec` (`backend/app/models/san_xuat.py:181`) đang nói **ngược lại**:
*"cập nhật lịch đẻ dòng mới ở phiên bản mới, KHÔNG sửa đè dòng cũ (giữ lịch sử)"*. Doc sai so với
code — phải sửa doc cùng đợt, dù chọn phương án nào.

Phần dễ: `thong_tin_goi` **đã trả sẵn** `phien_bans` (`release_update.py:203-212`), màn 3 đang lấy
về mà chỉ dùng hai cờ `cho_phep_thu_hoi` / `cho_phep_cap_nhat`.

### 1.5 Cột "Kế hoạch" ở Hồ sơ lệnh lệch +7 giờ

Cùng một dòng dữ liệu, hai màn hiện hai giờ khác nhau:

| | Cắt tờ, `du_kien_bat_dau` |
| --- | --- |
| DB | `2026-09-08 13:13:19+00` |
| Panel Xếp lịch 3 | `13:13` |
| Hồ sơ lệnh, cột Kế hoạch | `20:13` |

Nguyên nhân đã được ghi rõ sẵn trong `backend/app/services/gio_xuong.py:42-50`: giá trị trong DB là
**giờ tường dán nhãn UTC**; để nguyên nhãn thì Postgres trả `+00:00` và FE `new Date(iso)` cộng thêm
+7h. Quy ước này do họ xếp lịch đặt ra (`xep_lich_service._aware`, `:126-130` — *"FE gửi
`datetime-local` naive → coi là giờ nhà máy"*).

Cách vá đã có sẵn và đã áp cho bàn tổ: `lich_hien_thi()` cho thang LỊCH (`du_kien_*`) và
`thuc_te_hien_thi()` cho thang THỰC THI (`phien_chay`, `hoan_thanh_luc`). `bang_theo_doi.py` bọc
đúng (`:952`, `:1116`, `:1192`…). **`lenh_sx/ho_so.py:340-342` là chỗ sót** — trả thẳng cả
`du_kien_bat_dau`, `du_kien_ket_thuc` lẫn `hoan_thanh_luc`, không bọc gì.

Lưu ý: trừ 7 giờ đi thì **vấn đề ở §1.3 vẫn còn nguyên** (Cắt tờ 8/9 13:13 vẫn nằm trước Ghi kẽm
xong 9/9 14:16). Hai lỗi chồng nhau, phải vá cả hai.

---

## 2. Quyết định thiết kế

### 2.1 Panel có HAI chế độ, cắt theo trạng thái lệnh

- **Chưa phát hành** → giữ y nguyên hôm nay. Đúng §4: bảng bước chỉ có tên · máy/tổ · SL vào ·
  số người · giờ chạy; hai mốc của cả lệnh; không chặn gì.
- **Đã phát hành** → panel mọc thêm lớp thực tế: mỗi bước có trạng thái + giờ KH/TT, ô "Dự kiến
  xong" tách thành hai con số, ô mốc đổi nhãn (§2.4), thêm danh sách phiên bản (§2.5).

Cắt theo trạng thái chứ không thêm tab hay màn mới: `docs/design-xep-lich-3-ui.md` §3 chốt "không có
panel thứ tư, không có tab".

### 2.2 Dòng bước — ba lớp số

`CongDoanOut` mọc thêm (đều `None` khi lệnh chưa phát hành):

| Khoá | Nghĩa | Nguồn |
| --- | --- | --- |
| `trang_thai` | `released` / `running` / `paused` / `completed` | `cv.trang_thai` |
| `ke_hoach_bat_dau` · `ke_hoach_ket_thuc` | **cam kết đã đẩy xuống xưởng** ở phiên bản đang hiệu lực | `cv.du_kien_*`, bọc `lich_hien_thi()` |
| `thuc_bat_dau` | phiên chạy ĐẦU TIÊN của bước | `min(phien_chay.bat_dau)`, bọc `thuc_te_hien_thi()` |
| `thuc_ket_thuc` | mốc nghiệp vụ "xong lúc nào" | `cv.hoan_thanh_luc`, bọc `thuc_te_hien_thi()` |
| `lech_phut` | dương = trễ, âm = sớm | `thuc_ket_thuc − ke_hoach_ket_thuc`; bước đang chạy thì so `thuc_bat_dau` với `ke_hoach_bat_dau` |

Chỉ lấy công việc của **phiên bản gói đang hiệu lực** (`phien_ban_so == goi.version_hien_tai`) —
cùng luật `docs/spec-thuc-te-vs-ke-hoach.md` §2.1.

Nạp GỘP một lượt cho cả lô, không N+1: dùng lại `boi_canh.nap()` của Theo dõi sản xuất thay vì viết
đường đọc mới. `docs/spec-xep-lich-3.md` §4.1 đã chốt ràng buộc này ("cắt theo cửa sổ hoặc theo tập
`lsx_id`", "một truy vấn cho cả lô").

**Bẫy bắt buộc nhớ:** `response_model` của Pydantic **bỏ im lặng** mọi khoá service trả về mà schema
không khai — không lỗi, không log, FE nhận `undefined`. Thêm số nào phải đi hết dây:
dict service → `schemas/xep_lich_3.py` → type TS ở `api/client.ts` → JSX.

Hiển thị: dòng bước thêm một chip trạng thái và một dòng phụ `KH 13:13 → 14:15 · TT 14:15 → 14:16
(sớm 1 giờ)`. Bước chưa bắt đầu chỉ có dòng KH. **Không** đổi thứ tự bước — panel xếp theo thứ tự
chạy, khác Hồ sơ lệnh (xếp theo lớp phụ thuộc); hai màn cố ý khác nhau.

### 2.3 "Dự kiến xong" = neo lại theo điểm thật cuối cùng

Định nghĩa **điểm neo `A`**:

- bước đã `completed` → đóng góp `hoan_thanh_luc`;
- bước `running` / `paused` → đóng góp `max(bay_gio, giờ bắt đầu thật + phút chạy còn lại)`;
- `SAN = max(...)` trên mọi bước đã bắt đầu. Lệnh chưa có bước nào chạy → `SAN` không tồn tại.
- `A = max(SAN, moc)` nếu có `SAN`, ngược lại `A = moc`.

Rồi **trải lịch CHỈ các bước chưa bắt đầu** từ `A`. Bước đã xong không trải lại — nó nằm yên ở chỗ
nó đã xảy ra.

Panel bày **hai con số cạnh nhau**, không thay thế:

```
Kế hoạch (đã phát hành)   19:42 10/09     ← max(du_kien_ket_thuc) của gói đang hiệu lực
Dự kiến (theo thực tế)    17:30 10/09     ← trải lại từ A · sớm hơn 2 giờ 12 phút
```

Bỏ con số kế hoạch đi là mất luôn cái để so, và mất luôn thứ mà tổ dưới xưởng đang cầm.

**Ranh giới cứng:** con số dẫn xuất này **chỉ để đọc**. Nó KHÔNG ghi đè `du_kien_*` của gói đã phát
hành, KHÔNG tự dời mốc, KHÔNG tự đẩy lịch mới xuống xưởng — muốn đẩy thì vẫn phải bấm "Phát hành
cập nhật". Đúng `docs/spec-thuc-te-vs-ke-hoach.md` §2.1 (*"Máy không tự dời thanh… người điều độ
nhìn rồi tự kéo"*) và §3 (*"Không tự dời lịch theo thực tế"*).

Thanh trên Gantt của lệnh đã chạy dở: mép trái = **giờ bắt đầu THẬT** của bước đầu đã chạy, mép phải
= kết quả trải lại. Bước đã xong vẽ bằng sắc độ khác. Thanh vì thế **dài ra** khi mốc lùi về sau —
đúng như mong đợi.

### 2.4 Mốc của lệnh đã chạy dở = "bắt đầu PHẦN CÒN LẠI", có sàn

Đổi **nghĩa** của `xep_lich_lenh.bat_dau_at` theo trạng thái lệnh:

- lệnh **chưa có bước nào chạy**: mốc = bắt đầu cả lệnh. Giữ y nguyên hôm nay, không chặn gì (§1).
- lệnh **đã có bước chạy**: mốc = bắt đầu **phần chưa chạy**. Có **sàn cứng `SAN`** (§2.3).

`dat_moc` xử lý sàn theo đúng lối đang có cho ngoài-giờ-chạy — **trượt rồi báo**, không chặn cứng:

```
moc < SAN  ⇒  moc := SAN, rồi trượt tiếp vào đầu khoảng chạy được gần nhất
              da_doi = True
              thong_bao = "Đã có bước xong lúc 14:16 9/9 — không lùi lịch xuống dưới mốc đó."
```

Chặn cứng sẽ phá triết lý "không chặn gì" của cả màn; trượt-và-nói-ra thì vừa giữ được triết lý vừa
không đẻ ra lịch nằm trước quá khứ. Câu báo đi đúng đường của
`"Ngoài giờ chạy — đã dời sang {…}."` đang chạy tốt.

Nhãn trên panel phải đổi theo, không thì người dùng đọc con số `11/09` rồi tưởng cả lệnh dời sang
`11/09`:

```
BẮT ĐẦU PHẦN CÒN LẠI          ← thay "BẮT ĐẦU CHẠY MÁY" khi lệnh đã chạy dở
[ 11/09/2026 10:00 CH ]
Lệnh đã bắt đầu 9/9 18:38 · 1/9 việc đã xong
```

**Kéo theo — bốn nơi tiêu thụ mốc bước.** `services/xep_lich_3/moc.py` là cầu một chiều sang
`giu_cho_repo`, `ke_hoach_vat_tu_service`, `may_trang_thai.lenh_dang_chay`, `san_xuat/snapshot`.
Khi mốc đổi nghĩa thì `moc_theo_buoc()` phải trả **giờ thật cho bước đã chạy** và giờ dẫn xuất cho
bước còn lại — nếu không, "ngày cần" của vật tư và cột "máy đang chạy lệnh nào" sẽ nói theo một kế
hoạch không còn tồn tại. Đây là phần dễ bị bỏ sót nhất của cả đợt.

### 2.5 Lịch sử phiên bản — chọn bảng lịch sử, KHÔNG chọn đẻ dòng mới

Hai đường:

**A. Đẻ dòng `san_xuat_cong_viec` mới cho mỗi phiên bản** (đúng như docstring model đang hứa).
Đúng về nguyên lý, nhưng: `cong_viec.id` đang bị `san_xuat_phu_thuoc.nguon/dich_cong_viec_id`,
phân công, hỗ trợ, batch, bàn giao, KCS trỏ tới; đẻ dòng mới là phải trỏ lại hết, và **mọi** đường
đọc công việc phải mọc thêm bộ lọc `phien_ban_so = goi.version_hien_tai`. Rủi ro rải khắp tầng
thực thi, đổi lấy một tính năng chỉ để **xem**.

**B. Một bảng lịch sử, ghi TRƯỚC khi đè** ← **chọn cái này**.

```
san_xuat_cong_viec_lich_su
  id · goi_id · phien_ban_so · cong_viec_id
  may_id · du_kien_bat_dau · du_kien_ket_thuc
  created_at
```

- Ghi trong `phat_hanh_cap_nhat`, ngay trước ba dòng gán ở `release_update.py:267-269`: chụp giá trị
  **cũ** kèm `phien_ban_so` cũ.
- Dòng sống giữ nguyên id → không FK nào phải trỏ lại, không đường đọc nào phải sửa.
- Diff hai phiên bản = một truy vấn trên bảng này, ghép theo `cong_viec_id`.
- Bổ sung: `phat_hanh` lần đầu cũng ghi một lượt cho v1, không thì v1 trống.

Ràng buộc bắt buộc (CLAUDE.md): **không có Alembic** — cột/bảng mới phải viết vào
`backend/app/db_migrations.py`, và `docs/DB_SCHEMA.md` có guard test nên phải cập nhật **cùng lúc**,
không thì `init` đỏ.

**Phiên bản đã mất (v2…v7 của `GPH26-0001`) không dựng lại được.** Bảng lịch sử chỉ có tác dụng từ
lúc cài trở đi.

Giao diện, hai mức:

1. **Làm được ngay, không đổi gì:** danh sách phiên bản trong panel — `v8 · cập nhật · "Trả lịch về
   13h00 ngày 08/09" · admin · 18:37 10/09`. Dữ liệu đã nằm trong `thong_tin_goi.phien_bans`.
2. **Sau khi có bảng lịch sử:** bấm hai phiên bản → bảng so sánh từng bước
   `Cắt tờ: 8/9 13:13 → 8/9 20:13 · máy giữ nguyên`.

### 2.6 Vá +7 giờ — bọc đúng thang ở `ho_so.py`

`lenh_sx/ho_so.py:340-342` bọc lại:

- `du_kien_bat_dau`, `du_kien_ket_thuc` → `lich_hien_thi()` (thang LỊCH);
- `hoan_thanh_luc` → `thuc_te_hien_thi()` (thang THỰC THI).

Sau khi bọc, cột "Hoàn thành" vẫn ra đúng `14:16` như đang thấy, còn cột "Kế hoạch" lùi về `13:13`
khớp panel Xếp lịch 3. Không đổi quy ước lưu trữ — đổi quy ước là đụng cả họ xếp lịch lẫn dữ liệu
đã có, mà hệ chỉ chạy một múi giờ.

Rà thêm trong cùng đợt: mọi chỗ khác đọc `du_kien_*` hoặc `hoan_thanh_luc` rồi trả thẳng ra HTTP
(grep `du_kien_bat_dau` trong `app/services/`, `app/schemas/`). `bang_theo_doi.py` đã đúng, `ho_so.py`
là chỗ sót đã tìm ra; phải chắc không còn chỗ thứ ba.

---

## 3. Ngoài phạm vi — nói rõ để khỏi phình

- **Không** tự dời mốc / tự đẩy lịch mới xuống xưởng theo thực tế. Người điều độ nhìn rồi tự quyết.
- **Không** cho sửa giờ thực tế từ màn xếp lịch. Giờ thật chỉ do tầng thực thi đóng dấu.
- **Không** đụng cổng đóng nhóm, không sinh LSX bù (`spec-thuc-hien-san-xuat.md` §22).
- **Không** dựng lại các phiên bản đã mất.
- **Không** đổi quy ước lưu "giờ nhà máy dán nhãn UTC" của họ xếp lịch.
- **Không** thêm tab / panel thứ tư vào màn 3.

---

## 4. Thứ tự thi công đề nghị

| Đợt | Nội dung | Vì sao trước/sau |
| --- | --- | --- |
| 0 | §2.6 vá +7 giờ + rà các chỗ đọc `du_kien_*` | Độc lập, một chỗ sửa, đang làm sai số ngay trên màn người dùng đọc hằng ngày |
| 1 | §2.2 dòng bước KH/TT/lệch + §2.3 dự kiến động | Cùng đụng `ChiTietOut` và đường nạp bối cảnh; làm rời là sửa schema hai lần |
| 2 | §2.4 mốc phần-còn-lại + sàn, kèm `moc.py` trả giờ thật cho bước đã chạy | Dựa trên `SAN` mà đợt 1 đã dựng |
| 3 | §2.5 bảng lịch sử + migration + `DB_SCHEMA.md` + màn so sánh | Có migration, tách riêng để không kéo đợt 1–2 chờ |
| 3b | Sửa docstring `SanXuatCongViec` đang nói sai về giữ lịch sử | Đi kèm đợt 3 |

Danh sách phiên bản ở §2.5 mức 1 có thể ghép vào đợt 1 — nó không cần dữ liệu mới.

---

## 5. Bẫy cho người thi công

1. **Pydantic nuốt field im lặng.** Thêm khoá nào cũng phải đi hết dây dict → schema → TS → JSX,
   không thì FE nhận `undefined` mà không có lỗi nào.
2. **Hai thang giờ.** `du_kien_*` là giờ tường dán nhãn UTC; `phien_chay`/`hoan_thanh_luc` là UTC
   thật. Trừ hai cái đó cho nhau mà quên `ve_gio_xuong()` là lệch đúng 7 tiếng — và con số `lech_phut`
   sẽ sai theo đúng hướng khó phát hiện nhất (một ca làm việc).
3. **`_da_bat_dau_ids` soi HAI tín hiệu** (`release_update.py:66-73`): có phiên chạy **hoặc**
   `trang_thai != released`. Đừng tự viết lại bằng một tín hiệu.
4. **Bước lệch lần chạy.** `phat_hanh_cap_nhat` bỏ qua công việc không còn khớp lần chạy
   (`so_lech_phan_doan`); những dòng đó ở lại phiên bản CŨ. Bảng so sánh và bảng bước phải nói ra,
   không thì người đọc tưởng chúng đã được cập nhật.
5. **Sửa route/schema backend → RESTART uvicorn**, ở máy này không có hot-reload đáng tin.
6. **Xác minh bằng UI thật.** Luồng này có UI, nên phải thao tác lại bằng chuột/bàn phím trên
   dev-browser trước khi báo xong; không dùng API/curl thay bất kỳ bước nào.
