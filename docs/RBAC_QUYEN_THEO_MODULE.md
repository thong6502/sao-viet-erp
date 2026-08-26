# Quyền theo MODULE — bật ô này thì làm được gì

> Trả lời đúng một câu: *"cấp ô Xem cho Thu mua thì họ xem được gì?"*
>
> **Phạm vi: bốn phân hệ của đội mình** — Nhân sự & Lương · Mua hàng · Kế toán · Giao hàng
> (17 module). Module của đội khác (Kinh doanh · Sản xuất · Kho · Danh mục · Hệ thống) **không**
> nằm trong file này — số liệu bên đó mình không bảo đảm được, mà tài liệu quyền nói sai thì người
> đọc cấp nhầm.
>
> Vai trò nào đang có gì thì xem `RBAC_VAI_TRO.md`. File này nói về **ô quyền**, file kia nói về
> **người**.

---

## 1. Một dòng quyền gồm BA thứ, thiếu một là hiểu sai

```
       MODULE              ×        CỜ             ×      PHẠM VI
   (màn nào)                    (làm gì)              (thấy dữ liệu của ai)

   thu_mua                      can_read              own / department / all
   ↑ một MÀN = một dòng          ↑ 4 ô CRUD +          ↑ chọn ở dropdown
     trong ma trận                 ô chi tiết             cuối mỗi dòng
```

**Phạm vi quyết định THẤY BAO NHIÊU, không phải LÀM ĐƯỢC GÌ.** Cùng ô *Xem* nhưng:

| Phạm vi | Thấy |
|---|---|
| **Của tôi** | chỉ bản ghi do chính mình tạo / được giao |
| **Phòng ban** | mọi bản ghi của phòng mình (và tổ con) |
| **Tất cả** | toàn công ty |

⚠️ **Có màn KHÔNG có phạm vi.** 13 màn Cấu hình danh mục nằm trong `SCOPELESS_MODULES` —
chúng là bảng tra dùng chung, không thuộc về ai, nên dropdown Phạm vi không hiện. *(Cả 13 màn đó
là của đội khác; nhắc ở đây vì luật phạm vi là luật chung.)*

---

## 2. Bốn ô CRUD — nghĩa CHUNG, và vì sao vẫn phải đọc từng module

| Ô | Nghĩa chung |
|---|---|
| **Xem** | mở được màn + đọc danh sách trong phạm vi |
| **Thêm** | tạo bản ghi mới |
| **Sửa** | sửa bản ghi + các thao tác vòng đời **thường ngày** của màn đó |
| **Xoá** | xoá / ngừng dùng |

Nhưng **"Sửa" của mỗi màn gói việc khác nhau** — đó là chỗ hay hiểu nhầm nhất. Ví dụ:

- **Thu mua · Sửa** = lập/sửa/gửi duyệt PMH **và** đánh dấu đã mua / đã nhận.
- **Giao hàng · Sửa** = gửi yêu cầu giao **và** bấm *Đã lấy hàng*, nhập kết quả + số km —
  ba việc của ba người khác nhau, chung một ô.
- **Chấm công · Sửa** = ba tab cấu hình (Điểm chấm công · Khai ca · Lịch & Ngày lễ), **không** phải
  sửa công của ai.

Việc nào **nặng hoặc cần tách vai** thì được nhấc ra thành **ô chi tiết** riêng — xem §3.

---

## 3. Từng module — Xem thấy gì · Sửa làm được gì · ô chi tiết

> Nguồn: `frontend/src/components/PermissionMatrix.tsx` (`MODULE_HINT` + `FINE_ACTIONS`) — đúng
> chữ đang hiện trên màn Vai trò. Sửa ở đó thì sửa lại đây.

### 3.1 Thu mua

| Module | Xem thấy gì | Sửa làm được gì |
|---|---|---|
| **Mua hàng** (`thu_mua`) | danh sách **YCMH và PMH** trong phạm vi | lập/sửa/gửi duyệt PMH · đánh dấu đã mua / đã nhận |
| **Yêu cầu mua hàng** (`yeu_cau_mua_hang`) | màn **Yêu cầu mua hàng** (YCMH của các bộ phận) trong phạm vi | lập YCMH cho bộ phận mình · sửa khi còn nháp · huỷ |
| **Nhà cung cấp** (`nha_cung_cap`) | danh mục NCC + **bảng mặt hàng NCC đang bán** (tải mẫu, xuất Excel) | thêm/sửa NCC · ngừng dùng · **nhập bảng mặt hàng từ Excel** |

⚠️ **Màn YCMH mở cho BẢY ô, không riêng `yeu_cau_mua_hang`.** Báo giá · Kho · Sản xuất · Giấy ·
Kế toán · Mua hàng đều vào được bằng ô *Xem* của chính họ — cố ý, vì sáu nhóm đó đều phải xin vật
tư. Gác riêng `thu_mua` là khoá đường xin vật tư của năm nhóm còn lại.

⚠️ **`nha_cung_cap` còn mở tài khoản ngân hàng của NCC** ở màn Kế toán — người quản danh mục NCC
sửa được TK của họ **mà không cần** ô *Tài khoản ngân hàng*.

**Ô chi tiết:** `thu_mua` **không còn ô nào**. Hai ô cũ đã bỏ 12/08/2026:

- *"Sửa / đảo trạng thái đơn sau khi nhận hàng"* → ba việc nó gác (sửa số nhận · mở lại đơn · đóng
  đơn) là việc thường ngày của chính người lập phiếu, nay gộp vào ô **Sửa**.
- *"Huỷ PMH"* → **chưa bao giờ được đọc**. `purchase_service.cancel` gác bằng `ke_toan:approve`
  (hoặc chính người lập, khi phiếu còn nháp).

⚠️ **Duyệt / từ chối PMH KHÔNG nằm ở đây** — nó là ô chi tiết của **Kế toán** (§3.2), vì nút Duyệt
chỉ có ở màn Đơn mua hàng bên kế toán.

### 3.2 Kế toán

| Module | Xem thấy gì | Thêm / Sửa |
|---|---|---|
| **Đơn mua hàng** (`ke_toan`) | **CHỈ** màn Đơn mua hàng của kế toán (PMH đã duyệt, chờ chi) | — |
| **Phiếu chi** (`phieu_chi`) | màn Phiếu chi / UNC | **Thêm** = LẬP phiếu cọc, phiếu thanh toán, gán chứng từ |
| **Phiếu thu** (`phieu_thu`) | màn Phiếu thu | **Thêm** = LẬP / sửa phiếu thu, gán chứng từ |
| **Công nợ phải trả** (`cong_no_phai_tra`) | số còn nợ từng NCC — tính ra từ PMH + phiếu chi, **không có gì để sửa** | — |
| **Công nợ phải thu** (`cong_no_phai_thu`) | số khách còn nợ — chỉ phát sinh từ hoá đơn bán đã ghi nhận, trừ cọc cấn + phiếu thu. **Đơn mới chốt chưa tạo công nợ** | — |
| **Tài khoản ngân hàng** (`tk_ngan_hang`) | TK công ty + TK nhà cung cấp | thêm/sửa/ngừng dùng |

**Ô chi tiết:**

| Module | Ô | Việc |
|---|---|---|
| `ke_toan` | **Duyệt / từ chối PMH** ⚠️ | quyết phiếu có đi tiếp thành khoản chi hay không |
| `phieu_chi` | Huỷ phiếu chi chờ chi · In / xuất | |
| `phieu_thu` | Xác nhận đã thu tiền · Huỷ phiếu · In / xuất | |

⚠️ **Tách vai vẫn giữ:** có ô *Duyệt PMH* mà **không** có ô **Thêm** của Phiếu chi thì duyệt xong
vẫn **không tự viết được phiếu chi**. Đó là cố ý.

### 3.3 Nhân sự

| Module | Xem thấy gì | Sửa làm được gì |
|---|---|---|
| **Phòng ban** (`phong_ban`) | cây tổ chức phòng / tổ | thêm/sửa/xoá phòng ban |
| **Hồ sơ nhân sự** (`nhan_su`) | danh sách NV + chi tiết hồ sơ | thêm/sửa/xoá hồ sơ |
| **Chấm công** (`cham_cong`) | Bảng công tháng + Nhật ký chấm công trong phạm vi | **ba tab cấu hình**: Điểm chấm công · Khai ca · Lịch & Ngày lễ |
| **Nghỉ phép** (`nghi_phep`) | đơn nghỉ trong phạm vi | quản danh mục loại nghỉ |
| **Tăng ca** (`tang_ca`) | mục Tăng ca trên thanh bên + danh sách phiếu | |
| **Nội quy** (`noi_quy`) | đọc danh sách nội quy + mở file. **Vai mới sinh ra đã bật sẵn** | |

⚠️ **Lương & BHXH tách khỏi `nhan_su`** thành hai ô riêng (*Xem* và *Sửa*) vì là dữ liệu nhạy cảm.

⚠️ **Nhân viên tự làm việc của mình thì KHÔNG cần cấp gì:** tự gửi/huỷ đơn nghỉ, tự gửi/huỷ phiếu
tăng ca, tự xin phiếu đi muộn — tab luôn hiện. Chỉ khi muốn **duyệt của người khác** mới cần ô.

**Ô chi tiết `nhan_su`:** Xem lương & BHXH · Sửa lương & BHXH · Thao tác vòng đời (chính thức /
nghỉ / đình chỉ) · Điều chuyển & nâng bậc · Duyệt yêu cầu cập nhật · Xuất Excel.

**Ô chi tiết `cham_cong`:** Bảng công tháng · Duyệt phiếu đi muộn/về sớm/nghỉ nửa buổi · Điểm chấm
công · Khai ca · Lịch & Ngày lễ · Xem nhật ký · **Chấm bù / sửa công** · **Chốt kỳ công / Mở lại** ⚠️.

**Ô chi tiết `nghi_phep`:** Duyệt đơn ⚠️ · Quản danh mục loại nghỉ.
**Ô chi tiết `tang_ca`:** Duyệt phiếu tăng ca.

### 3.4 Lương

**Xem = MỞ MÀN Lương** — và chỉ thấy **hai tab của chính mình**: *Phiếu lương của tôi*, *Tạm ứng
của tôi*. **Không có ô này là không vào được màn, kể cả để xem phiếu lương của mình** ⇒ vai nào
cũng nên bật.

**Sửa** = gửi đề nghị tạm ứng / xin lương đợt 1 **cho chính mình**, và ghi ở những tab đã mở.

Mọi thứ còn lại là **ô chi tiết riêng**:

| Ô | Việc |
|---|---|
| Bảng lương tháng | mở bảng lương của người khác |
| Lương nhân viên | thang bậc / khung lương từng người |
| Lương khoán | đơn giá khoán theo tổ |
| Xem cấu hình lương | thang bậc, KPI, phụ cấp, bảo hiểm, lịch sử lương |
| Duyệt tạm ứng | |
| Xuất bảng lương / file chuyển khoản | |
| **Chốt bảng lương / Mở lại kỳ** ⚠️ | chốt kỳ **TOÀN CÔNG TY** — máy chủ còn đòi phạm vi **Tất cả** |
| **Đánh dấu đã chi lương** ⚠️ | tuyên bố **tiền đã ra tới tay người lao động**, khoá kỳ luôn. Máy chủ đòi phạm vi **Tất cả** |

⚠️ **Chốt** và **Đã chi** là **hai ô khác nhau** (tách 10/08/2026): người tính lương chốt số,
**kế toán** mới xác nhận đã trả. Muốn mở lại kỳ đã đánh dấu đã chi thì phải huỷ *đã chi* trước.

### 3.5 Giao hàng

| Module | Xem thấy gì | Sửa làm được gì |
|---|---|---|
| **Giao hàng** (`giao_hang`) | màn Giao hàng — tab *Đơn giao hàng*, lọc theo phạm vi | gửi yêu cầu giao từ đơn hàng bán · bấm *Đã lấy hàng* · nhập kết quả + số km |

**Ô chi tiết:** *Lên đơn giao hàng* (`can_plan`) — tab **Yêu cầu giao** + nút phân công tài xế ·
*Huỷ yêu cầu / huỷ chuyến* (`can_cancel`) — huỷ yêu cầu chưa lên kế hoạch hoặc huỷ chuyến đã xếp,
bắt nhập lý do và phiếu ở lại có vết · *Nhân viên giao hàng* (`can_view_drivers`) — tab thứ ba,
phơi lịch và KPI của **người khác** nên tách ô riêng.

Ô *Huỷ* bày lên ma trận 26/08/2026. Trước đó máy chủ đã gác bằng cờ này (`Canceller` ở
`routers/delivery.py`) và giao diện đã ẩn nút theo nó, nhưng bảng phân quyền **không có ô để
tick** ⇒ vai tạo tay trên giao diện không bao giờ huỷ được chuyến.

⚠️ **Kho KHÔNG cần ô `giao_hang`.** Yêu cầu xuất của Giao hàng hiện trong **Hộp yêu cầu của chính
kho**, đi theo ô **Kho**. Kho không thao tác gì trên màn Giao hàng.

⚠️ **Tài xế chỉ cần *Xem* + *Thao tác*, phạm vi *Của tôi*** (không *Huỷ* — bỏ chuyến là
quyết định của điều phối) — họ tự bấm *Đã lấy hàng* và nhập kết
quả cho chuyến của mình. Thiếu ô *Thao tác* thì họ vẫn nhận chuyến được, nhưng **quản lý phải bấm
hộ** (`da-lay-hang` / `ket-qua` gác bằng ô Thao tác, không đòi đúng người được phân).

⚠️ **Ai là tài xế = ai thuộc Bộ phận Giao hàng**, không phải ai có ô `giao_hang`. Bật cờ ở màn
**Phòng ban → Bộ phận Giao hàng**; ô chọn tài xế và tab Nhân viên cùng đọc một nguồn đó.

---

## 4. Ba cái bẫy hay mắc

**1. Bật cờ không có nghĩa là dùng được cờ đó.** Bảng `role_permissions` có **51 cột cờ dùng
chung cho mọi module**, nhưng mỗi module chỉ **đọc** vài cái. Hàm `_full()` lúc seed bật cả 51 cho
một module ⇒ Giám đốc có cờ *"Khai ca"* trên module *Khách hàng*, bật hay tắt đều **không đổi gì**.

> Danh sách cờ một module THẬT SỰ đọc: `FINE_ACTIONS` trong `PermissionMatrix.tsx`, cộng 4 ô CRUD.
> Script `backend/scripts/xuat_ma_tran_quyen.py` đọc thẳng file đó để lọc.

**2. Ô ở màn A nhưng tác dụng ở màn B.** *Duyệt PMH* là ô của **Kế toán**, không phải Thu mua.
Nguyên tắc từ 11/08/2026: **ô nằm ở đúng màn có cái nút** — để nhìn ma trận là đoán được nó làm gì.

**3. Một số ô đòi thêm phạm vi Tất cả.** *Chốt bảng lương* và *Đánh dấu đã chi lương* bật cờ thôi
chưa đủ — máy chủ còn kiểm phạm vi. Cấp cờ mà để phạm vi *Phòng ban* thì bấm vẫn bị chặn.

---

## 5. Cập nhật file này khi nào

Khi thêm/bớt một **ô quyền** hoặc đổi **chữ trên ma trận**. Nguồn sự thật là
`frontend/src/components/PermissionMatrix.tsx`; file này chỉ chép lại cho dễ đọc, nên hai bên lệch
thì **file kia đúng**.

Cả **17 module** của mình đều đã có chú giải trên giao diện. `yeu_cau_mua_hang` và
`nha_cung_cap` bổ sung 21/08/2026 — trước đó hai màn này không có dòng nào, người cấp quyền phải
tự đoán *"Xem cái này thì thấy gì"*.
