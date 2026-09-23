# Thiết kế — DẢI ROUTING trên bàn tổ (tổ thấy cả chuỗi, chỉ bấm bước của mình)

Trạng thái: **CHỐT HƯỚNG** (23/09/2026) — mục 1–7 chốt, mục 9 còn ba điểm mở chờ chủ dự án.
Phạm vi: màn **Thực hiện sản xuất → Bàn tổ** (`GET /api/san-xuat/work-items` với `nhom="lenh"`,
`frontend/src/pages/ThucHienSxPage.tsx`). KHÔNG đụng khâu phát hành, KHÔNG đụng snapshot.

---

## 0. Vì sao

Phát hành đóng băng cả chuỗi công đoạn của lệnh vào `san_xuat_cong_viec`, mỗi dòng một bước, mang
`department_id` của đúng tổ làm bước đó. Nhưng bàn tổ chỉ **lọc lấy bước của tổ mình**
(`san_xuat_repo.cong_viec_cua_lenh:588` nhận `department_ids` rồi `_pham_vi_to` cắt theo đó), nên
thẻ lệnh trên màn Tổ bế hiện đúng một dòng "Bế · 1 việc". Tổ không thấy:

- mình đứng thứ mấy trong lệnh, trước mình là ai, sau mình là ai;
- bước trước đã xong chưa, ra bao nhiêu, **đã giao sang chưa** (hai chuyện khác nhau);
- làm xong thì hàng đi đâu.

Thông tin ấy KHÔNG thiếu trong DB — nó nằm cùng gói phát hành, chỉ là chưa ai đọc ra. Hai mẩu duy
nhất đang lộ ra đều nằm trong drawer chi tiết, mỗi mẩu một hop:

- `dau_vao.cong_doan_truoc:171` — khối "Công đoạn trước" của tab Nhận (kế hoạch · thực tế · đã
  giao · đã xác nhận · chờ xác nhận · tên tổ). Đúng tinh thần, nhưng chỉ bước kề trước.
- `board.chi_tiet_cong_viec` → `ban_giao_chang_sau:1174` — danh sách đích giao, không phải để theo
  dõi.

Hệ quả thực tế ở xưởng: tổ phải hỏi miệng "in xong chưa" và "bế xong giao cho ai".

## 1. Cái tổ thấy (CHỐT)

Trên **mỗi thẻ lệnh** của bàn tổ, dưới dòng tiêu đề, thêm một **dải routing** — toàn bộ chuỗi công
đoạn của lệnh theo thứ tự, mỗi bước một ô:

| Ô | Nội dung |
|---|---|
| Bước của tổ mình | viền nhấn, nhãn "Tổ của bạn", tiến độ `đã làm / mục tiêu` |
| Bước khác | tên công đoạn · tổ giữ nó · trạng thái · số ra |

Ô bước khác **chỉ đọc**: không nút, không mở drawer, không bấm được. Mọi thao tác (Bắt đầu · Tạm
dừng · Kết thúc · ghi mẻ · bàn giao) vẫn nằm ở đúng chỗ cũ — hàng thao tác của bước mình.

Hai nhãn phụ đắt giá, cùng đọc từ bàn giao:

- Bước **kề trước** ghi thêm "Đã giao sang" khi có bàn giao đã xác nhận về bước mình. Phân biệt
  "bước trước xong rồi" với "xong rồi và hàng đã về tay tôi".
- Bước **kề sau** ghi "chờ bạn giao". Tổ biết đích trước khi mở form bàn giao.

Dưới dải, một dòng tóm tắt đầu vào: `Đã nhận {số} từ công đoạn trước`.

**Trần ghi mẻ KHÔNG lên dải** (đổi so với bản nháp ngày 23/09, sau khi dựng thật). Hai lý do:
`dau_vao.tran_ghi:67` lấy MIN qua các nhóm nguồn nên phải gọi `nhom_truoc` →
`cong_viec_chang_truoc`, 3-4 truy vấn cho TỪNG bước của tổ — một trang 20 lệnh là 80-160 truy vấn
thêm. Còn xấp xỉ nó bằng `đã nhận × hệ số` thì sai đúng ở bước ghép (nhiều nguồn), mà hai con số
khác nhau cho CÙNG một khái niệm là nói dối — chính bài học đã ghi ở `board.chi_tiet_cong_viec`.
Trần ở lại tab Nhận của drawer, nơi nó được tính đủ. Con số "đã nhận" thì rẻ và chính xác:
`tong_thuc_nhan_nhieu` đã gom sẵn cho cả trang, lọc theo đúng đơn vị đầu vào của bước.

Chú ý khi hiển thị: số "đã nhận" theo đơn vị ĐẦU VÀO, còn `don_vi` trên ô là đơn vị ĐẦU RA — dán
nhầm nhãn là tổ đọc ra con số khác hẳn, nên dòng này cố ý không kèm đơn vị.

Bước cuối lệnh: ô cuối ghi "KCS cuối" thay cho đích giao (`cong_viec.la_kcs_cuoi`).

## 2. Nguồn số — mỗi ô lấy từ đâu

Tất cả đọc từ **snapshot gói đang hiệu lực**, không đọc-sống routing (giữ đúng nguyên tắc mở đầu
`services/san_xuat/board.py`). Không thêm bảng, không thêm cột.

| Trường trên ô | Nguồn |
|---|---|
| Tên công đoạn | `san_xuat_cong_viec.ten_cong_doan` |
| Tổ giữ bước | `cong_viec.department_id` → `SanXuatRepository.to_ten_nhan` |
| Trạng thái | `cong_viec.trang_thai` (`released` · `running` · `paused` · `completed`) |
| Kế hoạch ra | `cong_viec.so_luong_ra` + `don_vi_ra` |
| Thực tế ra | `SanXuatSanLuongRepository.tong_tot_nhieu({cv.id})` — Σ mẻ tốt |
| Đã giao sang bước mình | `ban_giao_toi_dich(cv_cua_toi.id)`, chỉ trạng thái `xac_nhan`/`dieu_chinh` |
| Thứ tự trong dải | `LsxCongDoan.thu_tu` tra qua `step_key` |
| Trần ghi | `dau_vao.tran_ghi` (đã có) |

`san_xuat_cong_viec` KHÔNG có cột thứ tự — thứ tự phải tra `LsxCongDoan.thu_tu` bằng `step_key`.
Đừng sắp theo `du_kien_bat_dau` như `cong_viec_cua_lenh` đang làm cho danh sách việc: lệnh chưa đặt
giờ thì mốc trống, dải sẽ nhảy lung tung.

## 3. Ba hình dạng routing phải xử đúng

**Dải dài.** Chuỗi thật có thể tới mười mấy công đoạn, không vừa bề ngang. Luật (sửa 23/09/2026):
**hiện ĐỦ mọi bước**, hết chỗ thì XUỐNG DÒNG. Không cuộn ngang — màn xưởng thao tác bằng tay, cuộn
ngang là bẫy. Không gom "+N" nữa: bản đầu cắt cửa sổ 5 ô quanh bước của mình rồi gom hai đầu, nên
chuỗi 6 bước là giấu mất bước cuối — đúng thứ tổ cần thấy nhất ("hàng của tôi rồi đi đâu").

Lưới là **cột đều** (`repeat(auto-fit, minmax(150px, 1fr))`), không cho ô co theo chữ: co theo chữ
thì một hàng trông gọn hơn thật, nhưng vừa xuống dòng là hàng dưới lệch cột hẳn so với hàng trên,
đọc thành hai dải rời. Mốc nằm ở mép TRÁI ô, nên ô cuối sẽ thừa một quãng trống bên phải — quãng
đó giải bằng **đuôi + chốt** (mục 6), không bằng bề rộng ô.

**Bước tách lần chạy** (`phan_doan_so` / `phan_doan_tong`, mg `0254`). Một ô cho MỘT BƯỚC, không
phải một lần chạy — đúng luật `dau_vao._khoa:38` đã gom các lần chạy của cùng bước. Ô ghi "lần k/N"
khi `phan_doan_tong > 1`; trạng thái ô = trạng thái "yếu nhất" của các lần chạy (còn `released` ⇒
chờ làm; có `running` ⇒ đang chạy; hết `completed` ⇒ hoàn thành); số ra cộng dồn.

**Bài ghép.** Bước chạy chung mang `bai_ghep_cong_doan_id`, gộp nhiều bước lệnh
(`BaiGhepCongDoanMap`). Trong dải của MỘT lệnh, bước chung hiện MỘT ô, nhãn thêm "chạy chung" để tổ
hiểu vì sao số ra lớn hơn lệnh của mình. Thẻ nhóm theo bài ghép (`nguon_loai = "bai_ghep"`) thì dải
dựng theo routing của bài ghép, cùng luật.

## 4. Quyền đọc chéo tổ (CHỐT)

`_pham_vi_doc:56` chặn mở bàn của tổ ngoài phạm vi — luật đó **giữ nguyên**, dải routing không phải
cửa vòng để xem bàn tổ khác.

Mức đọc trên ô bước của tổ khác: **tên công đoạn · tổ · trạng thái · kế hoạch/thực tế ra · đã giao**.
Hết. KHÔNG lộ: người được phân công, mẻ, khoán, đơn giá, sự cố, ảnh KCS, vật tư. Mở đúng bấy nhiêu
là an toàn — khối "Công đoạn trước" đã lộ đúng bộ này từ 19/09 và không ai phản đối; nó cũng là thứ
tổ cần để tự điều việc.

Không cấp quyền mới. Dải hiện cho bất kỳ ai xem được bàn tổ ấy, vì nó là ngữ cảnh của chính việc
người đó được xem.

## 5. Hợp đồng API

Mở rộng `GET /api/san-xuat/work-items?nhom=lenh` (`routers/san_xuat.py:366`), thêm khoá `routing`
cho mỗi phần tử của mảng `lenh`, cạnh `cong_viec` đang có:

```jsonc
{
  "nguon_loai": "lsx", "nguon_ma": "LSX26-0004", "so_viec": 1,
  "cong_viec": [ /* giữ nguyên — bước của tổ mình, đủ trường thao tác */ ],
  "routing": [
    {
      "thu_tu": 1, "step_key": "…", "ten_cong_doan": "In",
      "to_id": 12, "to_ten": "Nhóm in 5 màu",
      "la_cua_toi": false, "la_kcs_cuoi": false,
      "trang_thai": "completed",
      "phan_doan_tong": 1,
      "chay_chung": false,
      "ke_hoach": 5300.0, "thuc_te": 5300.0, "don_vi": "to",
      "da_giao_sang_toi": null
    },
    { "…": "…", "ten_cong_doan": "Bế", "la_cua_toi": true, "cong_viec_id": 88,
      "da_giao_sang_toi": 5220.0, "tran_ghi": 10440.0 }
  ]
}
```

`la_cua_toi` do máy chủ chốt (so `department_id` với phạm vi bàn đang mở), KHÔNG để FE tự suy —
bàn cấp trên gom nhiều tổ trực thuộc thì "của tôi" là nhiều ô.

`cong_viec_id` CHỈ có trên ô của mình; ô tổ khác không mang id để FE không có đường mở drawer.

**Hiệu năng — bắt buộc.** Một trang bàn tổ có tới 20 lệnh. Mọi truy vấn của dải gom theo **cả
trang**, không nhân theo lệnh:

1. mọi `san_xuat_cong_viec` thuộc các `goi_id` của trang, KHÔNG lọc `department_id`
   (hàm mới cạnh `cong_viec_cua_lenh`, tái dùng nhánh OR theo `lsx_id`/`bai_ghep_id` của nó);
2. `LsxCongDoan.thu_tu` theo `step_key` của cả trang một lượt;
3. bảng phủ bài ghép theo `lsx_id` của cả trang;
4. `tong_tot_nhieu` + `to_ten_nhan` + `tong_thuc_nhan_nhieu` + `ban_giao_toi_nhieu_dich` gom id
   cả trang (cùng cách `release.phat_hanh` gom `cong_doan_ids` để né N+1).

ĐO ĐƯỢC (23/09/2026): **7 truy vấn cho 1 lệnh và cũng 7 cho 3 lệnh** — hằng số theo số lệnh.
`test_so_truy_van_khong_tang_theo_so_lenh` chốt lại con số đó.

Đừng gọi `cong_viec_chang_truoc` / `cong_viec_chang_sau` / `ban_giao_toi_dich` trong vòng lặp:
mỗi lần là 3–4 truy vấn, nhân 20 lệnh × 5 bước là vỡ trang.

## 6. UI — BĂNG CHUYỀN (sửa 23/09/2026)

Bản đầu vẽ 5 **thẻ xám rời**, mỗi thẻ một chip trạng thái. Chạy thật thì hỏng ba chỗ: thẻ cao
bằng nhau nên ô ít chữ hở đáy; 5 chip viền-nền-icon xếp hàng ăn hết sự chú ý mà chỉ mang 1 bit
tin mỗi cái; và số bàn giao bị in **hai lần** ("Đã giao sang 1.200" ở ô nguồn + "Đã nhận 1.200 từ
công đoạn trước" ở dòng dưới). Tổng cộng ~190px chiều cao cho bốn mẩu tin.

Hình mới bám đúng thứ nó mô tả: lệnh là giấy chảy **một chiều** qua máy và **đổi đơn vị dọc
đường**. Nên dải là một **đường ray**:

- **Mốc trên ray** thay cho chip: một vòng tròn 20px mang icon trạng thái (`check` · `play` ·
  `pause` · `clock` — đúng bộ icon của pill, không đẻ bộ thứ hai). Hình khác nhau chứ không chỉ
  màu khác nhau, để người mù màu vẫn đọc được. Trạng thái còn được nói thành chữ cho trình đọc
  màn hình (`.thsx-ray__sr`).
- **Đoạn ray** giữa hai mốc: liền nét `--moss` = hàng đã đi qua; đứt nét `--rule` = chưa tới;
  đứt nét `--rust` ở đoạn ngay sau bước của tổ = **đang chờ chính tổ giao**.
- **Số bàn giao nằm TRÊN đoạn ray** ngay trước bước của tổ — đúng chỗ việc bàn giao xảy ra. Nhờ
  vậy bỏ được cả dòng "Đã nhận … từ công đoạn trước" lẫn nhãn "Đã giao sang" ở ô nguồn.
- **Chữ dưới mốc**: tên bước (`--fs-sm`/600) · tổ (`--fs-2xs`, `--ash-2`) · số + đơn vị. Trạng
  thái CHỈ viết thành chữ khi là `đang chạy` / `tạm dừng`; "xong" và "chờ làm" thì nét ray đã nói
  rồi, viết thêm chỉ là 5 nhãn xếp hàng.
- **Bước của tổ** là chỗ DUY NHẤT được "to tiếng": nền `--rust-soft` chạy dưới phần chữ, mốc có
  quầng rust, tên + "Tổ của bạn" màu `--rust-deep`. Mọi thứ còn lại nằm phẳng trên nền thẻ, không
  viền, không bóng, `cursor: default`.

Mọi màu lấy từ `tokens.css`. Bản đầu gõ hex thẳng (`#0369a1`, `#ccfbf1`, `#eef2f7`…) — đó là lý
do nó lạc khỏi hệ màu chung của phần mềm.

**Cuối chuyền có chốt.** Mốc ở mép trái ô nên nếu ray dừng ngay tại mốc cuối thì nhãn bước cuối
còn chạy tiếp sang phải — băng chuyền trông như cụt giữa thẻ. Luật: ô cuối vẫn vẽ đoạn ray chạy hết
bề ngang ô, kết thúc bằng một vạch chặn (`.thsx-ray__chot`). Thiếu vạch chặn thì cái đuôi đó lại
đọc ra "còn bước nữa chưa hiện" — ngược hẳn ý cần nói. Đuôi và chốt ăn theo trạng thái bước cuối:
xong thì liền nét màu rêu, chưa tới thì đứt nét xám. Chuỗi xuống dòng thì chốt nằm ở chỗ chuỗi thật
sự hết, giữa hàng cuối, không phải ở mép phải.

Bẫy màn xưởng phải né (theo `bay-giao-dien-dien-thoai-svn`): không `space-between` bóp chữ, không
ellipsis nuốt tên công đoạn, không lưới chia đều đè chữ ở bề ngang hẹp. **Dưới 900px ray DỰNG
ĐỨNG** (mốc trái, chữ phải) chứ không xếp cột: ray ngang ở bề ngang đó thì mỗi ô chỉ còn vài chục
pixel, dựng đứng vẫn giữ nguyên chiều chảy và dài bao nhiêu bước cũng chứa được. Đuôi và chốt lật
theo: đuôi chạy xuống dưới mốc cuối, chốt là vạch NGANG chặn đáy. Ở bề ngang hẹp khoảng hở giữa hai hàng chỉ ~12px nên số bàn giao
**không** treo lên đoạn ray nữa mà về hàng, đứng ngay trên tên bước nhận hàng.

Màn hình đọc được khi không có dải: lệnh một bước (`routing` đúng 1 phần tử) thì ẩn dải hẳn, khỏi
bày một ô lẻ.

## 7. Real-time — ĐÃ CÓ SẴN, KHÔNG PHẢI LÀM GÌ

Kiểm lại 23/09/2026: đường đẩy đã thông sẵn, không cần mở thêm đích như bản nháp đầu viết.

`routers/san_xuat.py:_phat_sse:122` dùng `hub.broadcast` — gửi MỌI kết nối, không lọc tổ — mỗi lần
có việc Bắt đầu / Tạm dừng / Kết thúc (`san_xuat_cong_viec_changed`), và `_phat_sse_ban_giao:136`
cũng broadcast. Ở FE, handler của `AppShell.tsx` rơi xuống `setQuoteTick` ở dòng 770 cho mọi loại
event không bị chặn sớm, mà `ThucHienSxPage` nhận đúng tick ấy làm `eventTick` (`AppShell.tsx:1401`)
rồi nạp lại bàn.

Nghĩa là tổ bế đang mở bàn sẽ tự nạp lại khi tổ in bấm Kết thúc, và dải đi theo. Việc DUY NHẤT phải
giữ: dải nằm trong CÙNG response `work-items`, không tách endpoint riêng — tách ra là nó không nằm
trong đường refetch sẵn có và phải tự nối lại tick.

KHÔNG thêm `hub.publish` đích danh cho dải: bước tổ khác đổi trạng thái không phải việc "gửi tới"
tổ này, không đáng một toast.

## 8. KHÔNG làm ở lát này

- Không cho bấm sang bước của tổ khác (mở drawer, giục việc, nhắn tin). Muốn giục thì đi đường
  người, không đẻ nút.
- Không sửa `dau_vao` / luật trần / luật cổng bắt đầu. Lát này chỉ **bày ra** thứ đã tính.
- Không thêm cột `thu_tu` vào `san_xuat_cong_viec`. Tra qua `step_key` là đủ và không phải viết
  migration (và snapshot đã khoá routing sau phát hành nên `thu_tu` không đổi dưới chân).
- Không đụng chế độ `nhom="phang"` và view Lịch — dải chỉ có nghĩa khi đã gom theo lệnh.

## 9. Ba điểm còn mở

1. ~~**Dải dài**~~ — ĐÃ CHỐT 23/09/2026: hiện đủ mọi bước, hết chỗ thì xuống dòng, lưới cột đều
   (mục 3). Không gom "+N", không cuộn ngang.
2. **Bước tách lần chạy**: đang chốt gộp một ô. Nếu tổ cần biết đích danh "lần 2 của In đang chạy"
   thì tách N ô và dải dài thêm — chỗ này nay chịu được vì đã cho xuống dòng.
3. **Mức đọc chéo tổ**: mục 4 đang chốt không lộ người/tiền/mẻ. Nếu muốn tổ thấy "ai đang chạy máy
   bước trước" thì đó là quyết định riêng, không suy ra từ luật hiện có.
