# SPEC — SƠ ĐỒ BÀI GHÉP & THÔNG SỐ IN DẪN XUẤT

> **Bài ghép là chỗ tập trung của khúc tờ** — xuyên LSX và xuyên đơn hàng. Mỗi lệnh giữ chuỗi
> công đoạn riêng cả trước lẫn sau in; NGƯỜI khai bước nào chạy chung (CTP/in/cán/bế), điểm TOẢ
> nằm sau bước gộp CUỐI. Anh em với `spec-quy-tac-binh-bai.md`, `spec-cong-doan.md`, `spec-thue-ngoai-giao-nhan.md`.

> ⚠️ **CẬP NHẬT (2026-08) — đọc trước:** mô hình "một node IN duy nhất" + cột `buoc_in_step_key`
> (§2.1, §3.2) ĐÃ BỊ THAY bằng lớp đè ĐA-CÔNG-ĐOẠN: `bai_ghep_cong_doan` + `bai_ghep_cong_doan_map`
> (neo `lsx_step_key`), người dùng tự gộp bước nào chung. Bước chế bản (prepress) bị loại khỏi
> chuỗi giấy. Các mục dưới mô tả THIẾT KẾ CŨ — giữ để tra lịch sử, KHÔNG phải hiện trạng.

---

## 1. Vì sao có spec này

Module Bài ghép đã chạy ở tầng dữ liệu và tầng xếp lịch, nhưng **màn hình chưa nói ra mô hình đó**:

- Mở màn Công đoạn của một lệnh đang ghép thì không thấy dấu vết bài ghép nào. Kế hoạch đổi máy
  in của lệnh mà không được cảnh báo tại chỗ — phải sang màn Xếp lịch mới lòi ra.
- Thông số in (khổ tờ in, số con) sau khi ghép **đã đổi chủ sang bài**, nhưng màn lệnh vẫn hiện
  số cũ của bài tính giá.
- Công thức số tờ của bài **thiếu hao các bước sau in** → bài cấp không đủ giấy.

Ba chuyện trên cùng một gốc: lấy **lệnh** làm trung tâm, trong khi ở mặt máy in trung tâm là
**tờ giấy**.

---

## 2. Mô hình đồ thị

```
   LSX A:   ○ → ○ ─────┐                 ┌───→ ○ → ○
                       ↓                 ↑
                     ┌──────┐            │
                     │  IN  │────────────┘
                     └──────┘
                       ↑                 │
   LSX B: ○ → ○ → ○ ───┘                 └───→ ○ → ○ → ○
```

- Node IN có **nhiều dây vào và nhiều dây ra**.
- Chuỗi trước in **giữ riêng từng lệnh** — kể cả bước chế bản. Chỉ tờ giấy trên máy in là chung.
- Chuỗi sau in tách theo lệnh, mỗi nhánh đi tới hạn giao riêng.

### 2.1 Đồ thị là DẪN XUẤT, không lưu cạnh

Dựng lúc đọc, từ ba nguồn đã có:

```
thành viên bài ghép  +  routing từng lệnh  +  vị trí bước in trong routing đó
```

**KHÔNG** thêm cạnh xuyên đơn vào `lsx_cong_doan_phu_thuoc`, và **giữ nguyên** luật cấm hiện tại
(*"Chỉ được phụ thuộc công đoạn thuộc cùng đơn hàng"*). Quan hệ ghép sinh từ **vật lý tờ giấy**,
bằng chứng là bản ghi thành viên — không phải quan hệ người dùng khai. Mở cửa cho cạnh xuyên đơn
là mở cửa cho người dùng khai bừa quan hệ giữa hai đơn không liên quan.

### 2.2 Hai kiểu hội tụ — vẽ cả hai

| | Ở node IN | Sau in |
|---|---|---|
| Vì sao | chung tờ giấy | chung sản phẩm (bìa + ruột một cuốn) |
| Bằng chứng | thành viên bài ghép | cạnh `lsx_cong_doan_phu_thuoc` |
| Phạm vi | xuyên đơn hàng | trong cùng đơn |
| Ai tạo | máy suy, không lưu | người kéo dây, có lưu |
| Xoá ở sơ đồ bài | không | không (sửa tại màn lệnh) |

Chỉ vẽ kiểu thứ nhất thì nhìn tưởng bìa in xong là xong, trong khi nó còn phải chờ ruột.

---

## 3. Nhận diện bước in

### 3.1 Hiện trạng — quy ước ngầm

```python
cd.nhom == "print" and cd.loai_buoc == "may"
```

Dùng ở `bai_ghep_service._co_cong_doan_in` và `xep_lich_service._sinh_dong(bo_qua_in=True)`.
Đủ dùng **chỉ khi mỗi lệnh có đúng một bước in máy**. Bốn ca vỡ:

| Ca | Hậu quả |
|---|---|
| Lệnh có **2 bước nhóm print** (in 2 mặt tách dòng, in nền + màu pha) | `bo_qua_in` bỏ **sạch** mọi bước print → cả hai lượt biến mất khỏi lịch |
| Bước kế hoạch **tự thêm**, không chọn từ danh mục (`nhom` null) | Không bao giờ được coi là in, dù tên là "In offset" |
| **In thuê ngoài** (`nhom=print`, `loai_buoc=thue_ngoai`) | Báo *"không có công đoạn in"* trong khi lệnh có bước in |
| Ghép xong mới **sửa/xoá bước in** | Không ai canh; bài vẫn nghĩ mình có bước in |

### 3.2 Neo tường minh bằng `step_key`

`bai_ghep_thanh_vien` **+1 cột**:

| Field | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `buoc_in_step_key` | string(40) | | Bước in của lệnh này chạy chung tờ |

**Vì sao `step_key` chứ không phải `id`:** `replace_routing` khớp hàng cũ với payload bằng
`old_by_key = {r.step_key: r}` — `step_key` sống qua mọi lần lưu routing, còn `id` thì hàng dựng
lại sinh id mới. Quyết định cũ *"bài ghép neo LSX, không neo công đoạn"* đúng với **id**, không
đúng với **step_key**.

**Cách điền — máy nêu, người quyết:**

- Thêm thành viên → máy suy sẵn bước `print` + `may` **đầu tiên**. Lệnh chỉ có một bước in (gần
  như tất cả) thì người dùng không phải làm gì.
- Lệnh có **từ hai bước in trở lên** → hỏi: *"LSX26-0005 có 2 lượt in — lượt nào chạy chung tờ này?"*
  Không đoán khi câu trả lời không hiển nhiên.

**Hệ quả:** `bo_qua_in` so `step_key` thay vì quét cả nhóm; sơ đồ cắt chuỗi trước/sau in bằng vị
trí bước đó trong routing; xoá bước in khi đang ghép có chỗ bám để chặn.

### 3.3 Giữ guard 1 LSX ≤ 1 bài

Neo theo bước **không** nhằm mở đường cho một lệnh tham gia nhiều bài. Guard cứng hiện tại giữ
nguyên.

---

## 4. Số tờ và ranh giới hao

### 4.1 Công thức cũ thiếu giấy

`tinh_so_to` hiện tính `số tờ tốt = max(ceil(SL đặt ÷ số con/tờ))`. Nó lấy **SL đặt** — số thành
phẩm giao khách — trong khi sau in còn gấp, bắt tay, vào keo, xén, mỗi bước hao theo định mức.

Ví dụ: lệnh 1.000 cuốn, ghép 2 con/tờ.

| | Số tờ |
|---|---|
| Bài cấp hiện tại | `ceil(1000 ÷ 2)` = **500** + hao canh máy/chạy do người khai |
| Chuỗi ngược của lệnh đòi | ~1.050 con vào bước in → **525** |

Hai con số không liên quan gì tới nhau. Đủ hay thiếu là tuỳ người khai `hao_hut_chay` — khai 0 là
thiếu chắc chắn, và không một dòng nào báo.

### 4.2 Công thức mới

```
số tờ tốt = max_i( ceil( nhu_cầu_con_tại_bước_in(lsx_i) ÷ so_con_tren_to_i ) )
tổng tờ  = số tờ tốt + hao_hut_setup + hao_hut_chay
```

`nhu_cầu_con_tại_bước_in` lấy từ chuỗi ngược của lệnh (đã gồm hao mọi bước sau in), tính với hệ số
con **của bài** (`so_con_tren_to`), không phải `lsx.so_con` cũ.

### 4.3 Ranh giới hao — mặt máy in

- **Bài chịu** hao của riêng bước in: `hao_hut_setup` (canh máy) + `hao_hut_chay`.
- **Lệnh chịu** hao các bước sau in, theo định mức danh mục công đoạn như hiện tại.

Tờ phế sinh trên máy in chung không tách được theo lệnh, nên để bài chịu. Hết chuyện đếm hai lần.

### 4.4 Dư và thiếu

Chuỗi số lượng của lệnh khi đã ghép **gãy làm hai đoạn**, nối tại bước in:

- Từ bước in trở về trước (tờ nguyên → xả → tờ in): số do **bài** ép xuống.
- Từ sau bước in trở đi: số do **SL đặt của lệnh** kéo ngược lên.

Chênh lệch tại chỗ nối:

| | Nghĩa | Xử lý |
|---|---|---|
| Bài cấp **>** nhu cầu | lệnh ra thừa | chip xám `dư 300 con` — thông tin |
| Bài cấp **<** nhu cầu | lệnh không đủ hàng giao | chip đỏ `thiếu 25 tờ` — **chặn** *Sẵn sàng xếp lịch* |

---

## 5. Thông số in là dẫn xuất khi đã ghép

| Bài ghép quyết (lệnh đọc theo) | Lệnh vẫn giữ |
|---|---|
| giấy · khổ **tờ in** · số con/tờ · máy in · hao canh máy + chạy · số tờ cấp | SL đặt · khổ **thành phẩm** · số trang / số tay · routing sau in · hạn giao |

Khổ **thành phẩm** không đụng tới — đó là thứ khách đặt. Chỉ mọi thứ thuộc về *tờ in* mới đổi chủ.

### 5.1 Ba luật

1. `lsx.so_con` khi đã ghép **đọc theo** `so_con_tren_to` của thành viên.
2. `so_manh_xa` **suy lại** từ khổ giấy nguyên của bài ÷ khổ tờ in của bài, **hiện ra cho người
   sửa đè** — xả thực tế đôi khi chừa nhíp, chừa gáy.
3. Sửa số con ở bài → **kéo lệnh chạy lại chuỗi ngược ngay**. Hiện `bai_ghep_service` chưa từng
   gọi sang `lsx_service`; phải dựng chỗ nối đó, không thì con số hai màn lệch nhau ngay lần gõ
   đầu tiên.

### 5.2 Gỡ khỏi bài

Thông số in **trả về bài tính giá gốc** (bố cục in riêng), kèm toast nói rõ *"Đã trả thông số in
về bài tính giá"* — để không ai tưởng số của bài còn giữ.

---

## 6. Luồng UI

### 6.1 Chọn lệnh — không đổi

Màn Bài ghép → tab *Công đoạn in chờ xếp* → tick lệnh → **Tạo bài ghép**. Lọc theo giấy vẫn là
cửa chính vì một tờ chỉ một loại giấy.

### 6.2 Trong bài — công tắc Sơ đồ / Bảng

Dùng lại công tắc đã có ở màn Công đoạn (`Sơ đồ DAG` ↔ `Bảng danh sách`), **mặc định Sơ đồ**.
Các khối form hiện tại (Thông tin chung · Giấy & số tờ · Thành viên) giữ nguyên ở tab Bảng — ai quen
gõ form thì vẫn gõ.

### 6.3 Bố cục sơ đồ

- Nhánh trước in **canh phải** để chụm vào node IN (nhánh dài ngắn khác nhau).
- Node IN neo **cột giữa cố định**.
- Nhánh sau in **canh trái**, trải ra.
- Mỗi lệnh một màu; đầu nhánh gắn `LSX26-0005 · An Phát · hạn 9/8`.

### 6.4 Node IN — sửa được

Bấm → panel phải (cùng kiểu drawer bước ở màn lệnh):

- Máy in · giấy · khổ tờ in · số mảnh xả · hao canh máy · hao chạy
- **Bảng thành viên**: mỗi dòng một lệnh — `số con/tờ` gõ được, cạnh đó `nhu cầu tờ` (máy tính,
  gồm hao) và `dư / thiếu`

Gõ số con → số tờ cấp tính lại ngay, chip dư/thiếu trên đầu từng nhánh nhảy theo. Không đợi Lưu.

### 6.5 Nhánh — chỉ đọc

Không sửa tại chỗ. Bấm một node → **nhảy sang màn lệnh, mở đúng bước đó**. Trên nhánh vẫn hiện
tổ, thời lượng, và **badge thuê ngoài** nếu bước đó gửi ra ngoài.

Tiền nhiệm ngoài bài (ruột sách) → **node bóng mờ viền đứt** kèm badge mã LSX, bấm nhảy sang.

Hai loại dây phân biệt được: dây tới IN là **máy suy** (không xoá ở đây), dây ở nhánh là **người
khai** (sửa tại màn lệnh).

### 6.6 Thêm / bớt thành viên

- **+ Thêm lệnh vào bài** cạnh node IN → picker hàng chờ **đã lọc sẵn theo giấy + khổ của bài**.
- Bỏ: nút `×` đầu nhánh → xác nhận → nhánh biến mất, số tờ tính lại.

### 6.7 Kiểm tương thích — ĐÃ GỠ (17/08/2026)

Bảng "Kiểm tương thích sản xuất" (máy tự kết luận *Phù hợp / Cần xác nhận / Không phù hợp* cho
giấy · mực · số mặt · khổ TP) **đã bỏ khỏi cả FE và BE**, cùng hướng với việc bỏ cảnh báo
`khac_giay` / `khac_so_mau` / `khac_so_mat` trước đó: điều kiện gộp CHỈ là cùng công đoạn, quy cách
thì người lập kế hoạch có nghiệp vụ đó — máy không phán hộ.

Bốn giá trị này vẫn về nguyên trong `detail_dict` và **bày ở bảng thành viên** (`giay_ten`,
`muc_a`/`muc_b`, `quy_cach_in`, `kho_tp`) để người tự so; chỉ mất phần máy kết luận.

### 6.8 Đường vào từ phía lệnh

Màn Công đoạn của lệnh đã ghép: node **In offset** hiện **dạng chung** — viền đứt, badge
`GB26-0001`. Bấm → sơ đồ bài, **focus sẵn nhánh của lệnh đó**.

Cùng một ngôn ngữ thị giác với node bước-LSX-khác: *node không thuộc quyền màn này thì viền đứt*.

### 6.9 Real-time

Mọi thay đổi đẩy SSE — sửa số con ở bài thì màn lệnh đang mở tự nhảy số + toast; sửa routing ở
lệnh thì sơ đồ bài cập nhật. Không bắt refresh.

---

## 7. Cổng chặn

| Tình huống | Xử lý |
|---|---|
| Thành viên **thiếu tờ** | Chặn *Sẵn sàng xếp lịch* — không phải cảnh báo mềm |
| **Xoá bước in** của lệnh đang ghép | Chặn: *"Lệnh đang trong bài GB26-0001 — gỡ khỏi bài trước khi bỏ bước in"* |
| Lệnh trong bài tự vào lịch | Đã chặn sẵn: *"lập kế hoạch qua bài ghép"* |
| 1 LSX vào 2 bài | Đã chặn sẵn — giữ nguyên |

---

## 8. Ngoài phạm vi — ghi lại để không quên

**Đếm kẽm.** Ghép 3 lệnh lên một tờ thì bình bài ra **một bộ kẽm của tờ ghép**, nhưng hiện mỗi
thành viên vẫn giữ bước chế bản riêng, mỗi bước đếm kẽm theo lệnh của nó → đếm thừa gấp ba.

Chốt: **chế bản giữ riêng từng lệnh**, hình sơ đồ không đổi. Chuyện đếm kẽm giải riêng ở bước chế
bản, thành spec khác.

---

## 9. Kèm theo

Thêm cột `buoc_in_step_key` → phải viết `backend/app/db_migrations.py` **và** cập nhật
`docs/DB_SCHEMA.md` cùng lúc, không thì guard test đỏ.

---

## 10. Bài ghép 2 — bản chạy song song (17/08/2026)

Bản dựng lại của chính module này, chạy **song song** với bản cũ trên **cùng dữ liệu** để so trực
tiếp trước khi thay. Không có bảng riêng, không có engine thứ hai.

### 10.1 Dùng chung tới đâu

`BaiGhep2Service(BaiGhepService)` và `BaiGhep2Repository(BaiGhepRepository)` — kế thừa, chỉ override
đúng ba điểm khác biệt bên dưới. Mọi số dẫn xuất, guard cấu trúc, gộp/tách, audit đều là code của
bản cũ. Sửa engine là **cả hai màn cùng đổi** — đó là chủ đích.

FE dùng chung `BaiGhepBuocChungForm.tsx` (form lượt chạy chung) và `BaiGhepDagCanvas`. Form nằm
file riêng chứ **không** export từ `BaiGhepSoDo.tsx` nữa: màn mới mà phụ thuộc ngược vào màn cũ thì
Đợt 2 xoá màn cũ là gãy. Form tự nạp `bai-ghep.css` + `ke-hoach-sx.css` để style đi theo component.

### 10.2 Ba điểm khác bản cũ

| | Bản cũ | Bài ghép 2 |
|---|---|---|
| Hàng chờ | lệnh `san_sang`, lọc theo giấy | thêm `nhap` + `cho_bo_sung`; **không** lọc giấy/khổ/màu/bước in |
| Ruột sách gấp tay | chặn mọi `la_gap_tay` | chỉ chặn khi `so_tay_moi_cuon > 1` |
| Tạo bài | 1 lệnh cũng tạo được | tối thiểu **2 lệnh**, không tự động gộp |

Ý đằng sau: bản cũ lọc sẵn cho người dùng nên giấu mất lệnh đáng lẽ ghép được; bản 2 bày hết rồi
để người lập kế hoạch quyết — máy chỉ ghi nhận.

### 10.3 Metadata của bài — `mg 0212`

`bai_ghep` thêm `ten` · `han_hoan_thanh_sx` · `is_rush` · `nguoi_phu_trach_id`. Bốn cột này
**khởi tạo một lần lúc tạo bài** (tên từ mã, hạn = MIN hạn thành viên, gấp = có thành viên gấp,
phụ trách = người tạo) rồi thành ô người dùng sửa được. Bài ghép sau đó **không** tự cập nhật theo
thành viên — thêm một lệnh gấp vào bài không tự bật lại cờ gấp.

Hệ quả cho migration: `is_rush` thêm kèm `DEFAULT FALSE` nên "người dùng đã tắt" và "chưa backfill"
cùng là `FALSE`. `_migrate_bai_ghep_2` chỉ suy lại cờ ở **đúng lượt tạo cột** (`added`), lần chạy
lại chỉ vá dòng `NULL`.

`mg 0212` cũng chốt `UNIQUE(bai_ghep_thanh_vien.lsx_id)` — luật "1 lệnh 1 bài" trước nay chỉ có ở
tầng service. Gặp dữ liệu trùng thì migration **báo đích danh `lsx_id` rồi dừng**, không tự chọn
bài để xoá: đó là quyết định nghiệp vụ.

### 10.4 Quyền và lộ trình thay thế

Module key `bai_ghep_2`, không có scope. Từ 18/08/2026 đây là màn Bài ghép **duy nhất**: nhãn trong
bảng `modules` là "Bài ghép" (bỏ số 2), khoá vẫn giữ hậu tố `_2` vì quyền trong DB thật neo theo
khoá — đổi khoá là mồ côi mọi dòng `role_permissions` đã cấp. Vai nào từng có màn cũ thì nay có màn
này (mg `0216` chép quyền rồi mới xoá khoá cũ; `seed.py`/`role_templates.py` cấp cho các vai chủ chốt).

⚠️ Module mới phải khai thêm vào `MODULE_GROUPS` của `PermissionMatrix.tsx`. Backend trả dòng ma
trận cho MỌI module trong bảng `modules`, nhưng khoá chưa map rơi vào nhóm "Khác" — mà nhóm này
**mặc định thu gọn khi chưa cấp gì** (`open = granted > 0`). Kết quả: dòng có tồn tại nhưng nằm
sau một tiêu đề đóng ở đáy trang ⇒ người quản trị không cấp được ⇒ menu không hiện ⇒ tưởng module
chưa dựng. `bai_ghep_2` dính đúng vậy, vá 18/08/2026 (thêm vào nhóm Sản xuất ngay dưới `bai_ghep`,
kèm `PHAM_VI_CHO_PHEP` khoá `["all"]` cho khớp `SCOPELESS_MODULES`).

- **Đợt 1 (xong):** hai module chạy song song, hai quyền riêng.
- **Đợt 2 (xong 18/08/2026, chủ chốt nghiệm thu "thay thế được rồi"):** mg `0216` chép quyền
  `bai_ghep` → `bai_ghep_2` (guard: thiếu một vai là `rollback` + dừng, KHÔNG xoá quyền cũ), rồi xoá
  khoá `bai_ghep` khỏi `role_permissions` + `modules` và đổi nhãn. Gỡ kèm: `routers/bai_ghep.py`
  (prefix `/api/bai-ghep`), 3 màn `BaiGhepPage`/`BaiGhepDetailView`/`BaiGhepSoDo`, `api.baiGhep`,
  mục menu cũ, khoá `bai_ghep` trong `SCOPELESS_MODULES`/`seed.py`/`role_templates.py`.
  - **Không mất dữ liệu:** hai màn dùng CHUNG bảng `bai_ghep`/`bai_ghep_thanh_vien`/`bai_ghep_cong_doan`.
  - **Engine ở lại:** `services/bai_ghep_service.py` + `repositories/bai_ghep_repo.py` + schemas +
    models là của chung, `bai_ghep_2.py` chạy trên đó — đừng nhầm là code chết.
  - Hai chỗ phải sửa trước khi xoá được: `_map` (lỗi nghiệp vụ → mã HTTP) vốn `import` NGƯỢC từ
    router cũ, đã dời hẳn vào `routers/bai_ghep_2.py`; `bai-ghep.css` là tài sản chung nên GIỮ,
    `BaiGhepBuocChungForm` đang nạp nó.
