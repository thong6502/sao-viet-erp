# SPEC — SƠ ĐỒ BÀI GHÉP & THÔNG SỐ IN DẪN XUẤT

> **Bài ghép là chỗ tập trung của khúc tờ** — xuyên LSX và xuyên đơn hàng. Mỗi lệnh giữ chuỗi
> công đoạn riêng cả trước lẫn sau in, chỉ gặp nhau tại **một node IN duy nhất**.
> Anh em với `spec-quy-tac-binh-bai.md`, `spec-cong-doan.md`, `spec-thue-ngoai-giao-nhan.md`.

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
Các khối form hiện tại (Thông tin chung · Giấy & số tờ · Thành viên · Kiểm tương thích) giữ nguyên
ở tab Bảng — ai quen gõ form thì vẫn gõ.

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

### 6.7 Kiểm tương thích gắn lên nhánh

Bảng so sánh giữ nguyên ở tab Bảng (nó là ma trận đối chiếu). Nhưng dòng `cần xác nhận` phải hiện
**chip vàng ngay trên nhánh liên quan** — ngồi nhìn sơ đồ mà phải nhớ sang bảng khác là mất.

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
