# Vai trò — mỗi vai sở hữu những quyền gì

> **Phạm vi: bốn phân hệ của đội mình** — Nhân sự & Lương · Mua hàng · Kế toán · Giao hàng.
> Module của đội khác (Kinh doanh · Sản xuất · Kho · Danh mục · Hệ thống) **không** nằm trong file
> này: số liệu bên đó mình không bảo đảm được, mà tài liệu quyền nói sai thì người đọc cấp nhầm.
>
> Ô quyền *nghĩa là gì* thì xem `RBAC_QUYEN_THEO_MODULE.md`. File này nói về **người**, file kia
> nói về **ô**.

---

## 1. Đọc file này thế nào

§4 là **ma trận sinh thẳng từ code** (`app/seed.ROLES`), không gõ tay — nên không lệch được với
thứ hệ thống thật sự cấp. Lấy bản mới:

```bash
cd backend && python -m scripts.xuat_ma_tran_quyen
python -m scripts.xuat_ma_tran_quyen thu_mua      # lọc tiếp theo khoá module
```

⚠️ **Đây là quyền lúc SEED — vai MẪU.** Vai đã sửa tay trên hệ thống thật thì khác. Muốn biết cái
đang chạy thì mở màn **Vai trò**, hoặc đọc bảng `role_permissions`.

⚠️ Ma trận **đã lọc bỏ cờ vô nghĩa**. `role_permissions` có 51 cột cờ dùng chung cho mọi module,
nhưng mỗi module chỉ đọc vài cái; hàm `_full()` lúc seed bật cả 51 nên Giám đốc "có" cờ *Khai ca*
trên module *Khách hàng* — bật hay tắt đều không đổi gì. Script chỉ in cờ module đó **thật sự
đọc**, bằng cách đọc `FINE_ACTIONS` bên `PermissionMatrix.tsx`.

---

## 2. Bốn phân hệ — ai đang giữ gì

### 2.1 Mua hàng

| Vai | Phạm vi PMH | Làm được |
|---|---|---|
| **Nhân viên mua hàng** | *Của tôi* | Xem · Thêm · Sửa. **Không xoá.** YCMH và Nhà cung cấp thì phạm vi *Tất cả* |
| **Trưởng bộ phận mua hàng** | *Phòng ban* | thêm **Xoá** |
| **Kế hoạch SX** | *Của tôi* | chỉ **Xem** — để biết vật tư đã đặt tới đâu |
| **Giám đốc** | *Tất cả* | đủ 4 ô |

⚠️ **Không vai mua hàng nào duyệt được PMH.** Ô *Duyệt / từ chối PMH* thuộc module **Kế toán** —
người mua lập phiếu, kế toán quyết chi. Tách vai cố ý.

### 2.2 Kế toán

**Chỉ một vai có module kế toán: Giám đốc.**

Hai vai mang tên "Kế toán" trong bộ mẫu **không có module kế toán nào**:

| Vai | Thực tế có gì |
|---|---|
| **Kế toán bán hàng** | Dashboard + **Đơn hàng bán** (ô *Ghi phiếu thu cọc*) — module của đội Kinh doanh |
| **Kế toán kho** | Dashboard + **Kho** + ba danh mục vật liệu — module của đội Kho |

⚠️ Nghĩa là **chưa ai ngoài Giám đốc duyệt được PMH, lập được phiếu chi / phiếu thu, hay xem được
công nợ**. Đây là khoảng trống của **bộ vai mẫu**, không phải của hệ thống — khai thêm một vai
*Kế toán công nợ* với `ke_toan` + `phieu_chi` + `phieu_thu` + hai màn công nợ là xong.

### 2.3 Nhân sự & Lương

| Vai | Có gì |
|---|---|
| **Trưởng phòng HCNS** | **6/7 module** của phân hệ: Phòng ban · Hồ sơ nhân sự · Chấm công · Nghỉ phép · Tăng ca · Lương — đủ ô nặng (chốt kỳ công, chốt bảng lương, đánh dấu đã chi) |
| **Nhân viên** | **3 module**, phạm vi *Của tôi*: Nghỉ phép · Tăng ca · Chấm công — mỗi cái **Xem · Thêm · Huỷ** (tự gửi, tự huỷ đơn của mình) |
| **Giám đốc** | cả 7, phạm vi *Tất cả* |

⚠️ **Hai lỗ hổng của bộ vai mẫu, đáng vá:**

1. **Vai "Nhân viên" không vào được màn Lương** — nó không có module `luong`. Mà theo đúng chú
   giải của hệ thống: *"Không có ô này là không vào được màn, **kể cả để xem phiếu lương của
   mình**"*. Người lao động dùng vai này **không xem được phiếu lương của họ**.
2. **Chỉ Giám đốc có `noi_quy`** — Trưởng phòng HCNS thì không, trong khi nội quy lao động là
   thứ ai cũng phải đọc và HCNS mới là người quản tài liệu đó. (Vai tạo mới trên giao diện được
   bật sẵn ô này; vai seed thì không.)

### 2.4 Giao hàng

| Vai | Có gì |
|---|---|
| **Giám đốc** | Xem · Thêm · Sửa · Xoá · **Lên đơn giao hàng** · **Nhân viên giao hàng** |

⚠️ **Bộ vai mẫu chưa có vai giao hàng nào.** Hai vai đang dùng để chạy thử —
*Quản lý giao hàng* và *Tài xế giao hàng* — do `scripts/seed_giao_hang_demo.py` tạo, **không** nằm
trong `seed.ROLES`, nên không có trong §4:

| Vai (từ script chạy thử) | Ô | Phạm vi |
|---|---|---|
| **Quản lý giao hàng** | Xem · Thao tác · Lên đơn giao hàng · Nhân viên giao hàng · Huỷ | *Tất cả* |
| **Tài xế giao hàng** | Xem · Thao tác | *Của tôi* — chỉ thấy chuyến của chính mình |

Muốn dùng thật thì khai hai vai này trong `seed.ROLES`, hoặc tạo tay trên màn Vai trò.

---

## 3. Nhìn nhanh: vai nào chạm phân hệ nào

| Vai | NS & Lương | Mua hàng | Kế toán | Giao hàng |
|---|---|---|---|---|
| Giám đốc | ✅ đủ | ✅ đủ | ✅ đủ | ✅ đủ |
| Trưởng phòng HCNS | ✅ 6/7 | — | — | — |
| Nhân viên | ⬤ 3 (của tôi) | — | — | — |
| Trưởng bộ phận mua hàng | — | ✅ | — | — |
| Nhân viên mua hàng | — | ⬤ không xoá | — | — |
| Kế hoạch SX | — | ⬤ chỉ xem | — | — |
| Kế toán bán hàng · Kế toán kho | — | — | ❌ **không có** | — |

*(Các vai Sản xuất / Kinh doanh còn lại chỉ chạm phân hệ của mình ở mức xem — xem chi tiết ở §4.)*

---

## 4. Ma trận đầy đủ — chỉ 4 phân hệ của mình

*(sinh từ `app/seed.ROLES`; chạy `python -m scripts.xuat_ma_tran_quyen` để lấy bản mới. Vai nào
không chạm phân hệ nào của mình thì không xuất hiện ở đây.)*

### Giám đốc  ·  phòng Ban giám đốc

*Nhân sự & Lương*
- **Phòng ban** (`phong_ban`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá · Đặt trưởng phòng · Đổi cấp trên
- **Hồ sơ nhân sự** (`nhan_su`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá · Xuất file · Duyệt · Đổi trạng thái · Điều chuyển / chuyển phòng · Xem lương & BHXH · Sửa lương & BHXH
- **Chấm công** (`cham_cong`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá · Khoá / Chốt kỳ · Chấm bù / sửa công · Xem nhật ký · Bảng công tháng · Duyệt đi muộn / về sớm · Điểm chấm công · Khai ca · Lịch & Ngày lễ
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá · Duyệt · Danh mục loại nghỉ
- **Tăng ca** (`tang_ca`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá · Duyệt
- **Lương** (`luong`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá · Xuất file · Duyệt · Đổi trạng thái · Khoá / Chốt kỳ · Xem lương & BHXH · Bảng lương tháng · Lương nhân viên · Lương khoán
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem · Thêm · Xoá

*Mua hàng*
- **Yêu cầu mua hàng** (`yeu_cau_mua_hang`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá
- **Mua hàng** (`thu_mua`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá
- **Nhà cung cấp** (`nha_cung_cap`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá

*Kế toán*
- **Đơn mua hàng (Kế toán)** (`ke_toan`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá · Duyệt
- **Phiếu chi / UNC** (`phieu_chi`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá · Xuất file · Huỷ
- **Phiếu thu** (`phieu_thu`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá · Xuất file · Đổi trạng thái · Huỷ
- **Công nợ phải trả** (`cong_no_phai_tra`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá
- **Công nợ phải thu** (`cong_no_phai_thu`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá
- **Tài khoản ngân hàng** (`tk_ngan_hang`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá

*Giao hàng*
- **Giao hàng** (`giao_hang`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá · Lên đơn giao hàng · Nhân viên giao hàng

### Trưởng phòng HCNS  ·  phòng Hành chính nhân sự

*Nhân sự & Lương*
- **Phòng ban** (`phong_ban`) — phạm vi *Tất cả*  
  Xem
- **Hồ sơ nhân sự** (`nhan_su`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xem lương & BHXH · Sửa lương & BHXH · Đổi trạng thái · Điều chuyển / chuyển phòng · Duyệt · Xuất file
- **Chấm công** (`cham_cong`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá · Khoá / Chốt kỳ · Chấm bù / sửa công · Xem nhật ký · Bảng công tháng · Duyệt đi muộn / về sớm · Điểm chấm công · Khai ca · Lịch & Ngày lễ
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá · Duyệt
- **Tăng ca** (`tang_ca`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Duyệt
- **Lương** (`luong`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá · Xuất file · Duyệt · Đổi trạng thái · Khoá / Chốt kỳ · Xem lương & BHXH · Bảng lương tháng · Lương nhân viên · Lương khoán

### Nhân viên  ·  phòng Hành chính nhân sự

*Nhân sự & Lương*
- **Chấm công** (`cham_cong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Tăng ca** (`tang_ca`) — phạm vi *Của tôi*  
  Xem · Thêm

### Kế hoạch SX  ·  phòng Sản xuất

*Nhân sự & Lương*
- **Phòng ban** (`phong_ban`) — phạm vi *Tất cả*  
  Xem
- **Chấm công** (`cham_cong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Tăng ca** (`tang_ca`) — phạm vi *Của tôi*  
  Xem · Thêm

*Mua hàng*
- **Yêu cầu mua hàng** (`yeu_cau_mua_hang`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa
- **Mua hàng** (`thu_mua`) — phạm vi *Của tôi*  
  Xem

### Tổ trưởng SX  ·  phòng Sản xuất

*Nhân sự & Lương*
- **Chấm công** (`cham_cong`) — phạm vi *Phòng ban*  
  Xem · Duyệt đi muộn / về sớm
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Phòng ban*  
  Xem · Thêm · Duyệt
- **Tăng ca** (`tang_ca`) — phạm vi *Phòng ban*  
  Xem · Thêm · Sửa · Duyệt

*Mua hàng*
- **Yêu cầu mua hàng** (`yeu_cau_mua_hang`) — phạm vi *Phòng ban*  
  Xem · Thêm · Sửa

### Thợ sửa chữa  ·  phòng Sản xuất

*Nhân sự & Lương*
- **Chấm công** (`cham_cong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Tăng ca** (`tang_ca`) — phạm vi *Của tôi*  
  Xem · Thêm

### Thợ SX  ·  phòng Sản xuất

*Nhân sự & Lương*
- **Chấm công** (`cham_cong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Tăng ca** (`tang_ca`) — phạm vi *Của tôi*  
  Xem · Thêm

### QC  ·  phòng Sản xuất

*Nhân sự & Lương*
- **Chấm công** (`cham_cong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Tăng ca** (`tang_ca`) — phạm vi *Của tôi*  
  Xem · Thêm

### Trưởng phòng KD  ·  phòng Kinh doanh

*Nhân sự & Lương*
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Của tôi*  
  Xem · Thêm

### Giám đốc Kinh doanh  ·  phòng Kinh doanh

*Nhân sự & Lương*
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Của tôi*  
  Xem · Thêm

### NV Sales  ·  phòng Kinh doanh

*Nhân sự & Lương*
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Của tôi*  
  Xem · Thêm

### Thủ kho  ·  phòng Kho

*Mua hàng*
- **Yêu cầu mua hàng** (`yeu_cau_mua_hang`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa

### Quản lý kho  ·  phòng Kho

*Mua hàng*
- **Yêu cầu mua hàng** (`yeu_cau_mua_hang`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa

### Nhân viên sản xuất  ·  phòng Sản xuất

*Mua hàng*
- **Yêu cầu mua hàng** (`yeu_cau_mua_hang`) — phạm vi *Của tôi*  
  Xem · Thêm · Sửa

### Quản lý sản xuất  ·  phòng Sản xuất

*Mua hàng*
- **Yêu cầu mua hàng** (`yeu_cau_mua_hang`) — phạm vi *Phòng ban*  
  Xem · Thêm · Sửa

### Nhân viên mua hàng  ·  phòng Mua hàng

*Mua hàng*
- **Yêu cầu mua hàng** (`yeu_cau_mua_hang`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa
- **Mua hàng** (`thu_mua`) — phạm vi *Của tôi*  
  Xem · Thêm · Sửa
- **Nhà cung cấp** (`nha_cung_cap`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa

### Trưởng bộ phận mua hàng  ·  phòng Mua hàng

*Mua hàng*
- **Yêu cầu mua hàng** (`yeu_cau_mua_hang`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá
- **Mua hàng** (`thu_mua`) — phạm vi *Phòng ban*  
  Xem · Thêm · Sửa · Xoá
- **Nhà cung cấp** (`nha_cung_cap`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá
