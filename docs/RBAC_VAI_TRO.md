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

| Vai | Thực tế có gì |
|---|---|
| **Kế toán tổng hợp** | **Phiếu chi** · **Phiếu thu** (lập · sửa · huỷ · in) · **hai màn Công nợ** · **Tài khoản ngân hàng** (xem + sửa số dư) · **Lương** (bảng lương tháng · đánh dấu đã chi · xuất file) · Đơn mua hàng (Kế toán) **chỉ xem** |
| **Kế toán bán hàng** | Dashboard + **Đơn hàng bán** (ô *Ghi phiếu thu cọc*) — module của đội Kinh doanh |
| **Kế toán kho** | Dashboard + **Kho** + ba danh mục vật liệu — module của đội Kho |
| **Giám đốc** | đủ cả 6 màn, phạm vi *Tất cả* |

Vai **Kế toán tổng hợp** thêm 26/08/2026 — trước đó 5 màn tách khỏi khoá `ke_toan` ngày
10/08/2026 (Phiếu chi · Phiếu thu · hai màn Công nợ · Tài khoản ngân hàng) không vai nào cầm
ngoài Giám đốc, tức người làm kế toán không mở nổi màn của chính mình. Bộ ô bám đúng vai mẫu
`ke_toan` trong `services/role_templates.py` — thứ ma trận đang chào admin khi tạo vai mới.

⚠️ **Kế toán tổng hợp KHÔNG duyệt được PMH.** Ô *Duyệt / từ chối PMH* (`ke_toan:approve`) vẫn
chỉ Giám đốc giữ — cùng luật tách vai với phân hệ Mua hàng ở §2.1: người đề xuất không tự duyệt,
người ghi sổ không tự quyết chi.

### 2.3 Nhân sự & Lương

| Vai | Có gì |
|---|---|
| **Trưởng phòng HCNS** | **cả 7 module** của phân hệ: Phòng ban · Hồ sơ nhân sự · Chấm công · Nghỉ phép · Tăng ca · Lương · Nội quy — đủ ô nặng (chốt kỳ công, chốt bảng lương, đánh dấu đã chi) |
| **Nhân viên** | **3 mô-đun khai riêng**, phạm vi *Của tôi*: Nghỉ phép · Tăng ca · Chấm công — mỗi cái **Xem · Thêm · Huỷ** (tự gửi, tự huỷ đơn của mình), cộng ba ô mặc định bên dưới |
| **Giám đốc** | cả 7, phạm vi *Tất cả* |

✅ **Ba ô cấp SẴN cho MỌI vai** (`seed.quyen_mac_dinh`), nên §4 vai nào cũng thấy hai dòng cuối:

| Ô | Phạm vi | Để làm gì |
|---|---|---|
| `self_service` | *Của tôi* | tự chấm công, tự gửi đơn nghỉ / tăng ca / tạm ứng |
| `noi_quy` | *Tất cả* | đọc nội quy lao động — ai cũng phải đọc |
| `luong` | *Của tôi* | mở màn Lương ở phần cá nhân: phiếu lương của mình + xin tạm ứng |

Đây là bản vá của hai lỗ hổng từng ghi ở đây (vai "Nhân viên" không mở được màn Lương · chỉ
Giám đốc có `noi_quy`): cả ba là Ô THẬT trên bảng phân quyền, HCNS **tắt được** cho vai nào cần
siết. Vai nào khai riêng một trong ba khoá thì bản khai riêng thắng — ví dụ *Kế toán tổng hợp*
khai `luong` phạm vi *Tất cả* nên mất phần mặc định, phải tự cộng lại `can_create`.

### 2.4 Giao hàng

| Vai | Ô | Phạm vi |
|---|---|---|
| **Quản lý giao hàng** | Xem · Thao tác · Sửa · **Lên đơn giao hàng** · **Nhân viên giao hàng** · **Huỷ** | *Tất cả* |
| **Nhân viên giao hàng** (tài xế) | Xem · Thao tác | *Của tôi* — chỉ chuyến của chính mình |
| **Giám đốc Kinh doanh** | Xem · Thao tác · Huỷ | *Tất cả* |
| **Trưởng phòng KD** | Xem · Thao tác · Huỷ | *Phòng ban* |
| **NV Sales** | Xem · Thao tác | *Của tôi* |
| **Giám đốc** | đủ | *Tất cả* |

Hai vai khối Giao hàng thêm 26/08/2026 theo đúng hai persona của `docs/prd-giao-hang.md` §3:
người **điều phối** và người **chạy xe**. Khối Kinh doanh được cấp kèm vì người bán là người
GỬI yêu cầu giao và phải theo dõi hàng của khách mình tới đâu — nhưng **không** `can_plan`, tức
không tự xếp được lịch tài xế.

⚠️ **Phạm vi của Quản lý giao hàng phải là *Tất cả*, đừng hạ xuống *Phòng ban*.** Bộ lọc phạm vi
của yêu cầu giao hàng soi `department_id` của **NGƯỜI TẠO** (Kinh doanh), nên vai ở phòng Giao
hàng mà để *Phòng ban* sẽ không thấy MỘT yêu cầu nào. Xem
`delivery_service.chan_ngoai_pham_vi_yeu_cau`.

⚠️ **Tài xế phải là nhân sự của phòng có cờ *Bộ phận Giao hàng*.** Cấp vai thôi chưa đủ: tab
"Nhân viên giao hàng" và ô chọn tài xế lấy danh sách từ **hồ sơ nhân sự** thuộc phòng được
tick cờ đó (`_ai_la_tai_xe` ở `routers/delivery.py`) — không có bảng tài xế riêng. Chưa phòng nào
được tick thì hệ thống lùi về quy tắc "ai mở được màn thì là tài xế".

⚠️ `scripts/seed_giao_hang_demo.py` (script chạy thử đời cũ) tạo hai vai **trùng tên** ngoài
`seed.ROLES` và gắn vào phòng đầu tiên trong DB — đừng chạy nữa, sẽ đẻ vai trùng ở sai phòng.

Kho **không cần** ô `giao_hang`: ba nút của kho gác bằng ô `kho` sẵn có, vì đề nghị xuất hàng sống
trong Hộp yêu cầu mà kho vẫn mở hằng ngày.

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
| Kế toán tổng hợp | ⬤ Lương (bảng tháng · đã chi) | ⬤ chỉ xem | ✅ trừ *Duyệt PMH* | — |
| Kế toán bán hàng · Kế toán kho | — | — | ❌ **không có** | — |
| Quản lý giao hàng | — | — | — | ✅ đủ (*Tất cả*) |
| Nhân viên giao hàng | — | — | — | ⬤ xem + thao tác (*Của tôi*) |
| Giám đốc KD · TP KD · NV Sales | — | — | — | ⬤ gửi yêu cầu + theo dõi |

*(Các vai Sản xuất / Kinh doanh còn lại chỉ chạm phân hệ của mình ở mức xem — xem chi tiết ở §4.)*

---

## 4. Ma trận đầy đủ — chỉ 4 phân hệ của mình

*(sinh từ `app/seed.ROLES` **cộng ba ô mặc định** `seed.quyen_mac_dinh` — chạy
`python -m scripts.xuat_ma_tran_quyen` để lấy bản mới. Đừng sửa tay phần này. Vai nào cũng có
`luong` (*Của tôi*) và `noi_quy` nên vai nào cũng xuất hiện ở đây, kể cả vai chỉ chạm phân hệ
của đội khác.)*

> **Hai vai của khối xưởng có bản sao ở TỪNG TỔ.** Vai trò thuộc về đúng một phòng ban, mà thợ
> lại nằm trong tổ (Tổ In offset, Tổ Chế bản…) chứ không nằm ở phòng "Sản xuất". Nên `seed_vai_theo_to`
> chép **Tổ trưởng SX** và **Thợ SX** xuống từng tổ, nguyên bộ ô như bản dưới đây, rồi trỏ người
> của tổ sang vai của chính tổ mình. Không chép thì mở một tổ trên màn Phòng ban sẽ thấy tab Vai
> trò trống trơn và không gán lại vai cho thợ được (`assign_role` bắt vai phải cùng phòng với người).

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
- **Báo cáo công nợ** (`bao_cao_cong_no`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá (Sửa = khoá/mở kỳ kế toán công nợ)
- **Tài khoản ngân hàng** (`tk_ngan_hang`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá

*Giao hàng*
- **Giao hàng** (`giao_hang`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá · Huỷ · Lên đơn giao hàng · Nhân viên giao hàng

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
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

### Nhân viên  ·  phòng Hành chính nhân sự

*Nhân sự & Lương*
- **Chấm công** (`cham_cong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Tăng ca** (`tang_ca`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

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
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

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
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

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
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

### Thợ SX  ·  phòng Sản xuất

*Nhân sự & Lương*
- **Chấm công** (`cham_cong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Tăng ca** (`tang_ca`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

### QC  ·  phòng Sản xuất

*Nhân sự & Lương*
- **Chấm công** (`cham_cong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Tăng ca** (`tang_ca`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

### Trưởng phòng KD  ·  phòng Kinh doanh

*Nhân sự & Lương*
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

*Giao hàng*
- **Giao hàng** (`giao_hang`) — phạm vi *Phòng ban*  
  Xem · Thêm · Huỷ

### Giám đốc Kinh doanh  ·  phòng Kinh doanh

*Nhân sự & Lương*
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

*Giao hàng*
- **Giao hàng** (`giao_hang`) — phạm vi *Tất cả*  
  Xem · Thêm · Huỷ

### NV Sales  ·  phòng Kinh doanh

*Nhân sự & Lương*
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

*Giao hàng*
- **Giao hàng** (`giao_hang`) — phạm vi *Của tôi*  
  Xem · Thêm

### Thủ kho  ·  phòng Kho

*Nhân sự & Lương*
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

*Mua hàng*
- **Yêu cầu mua hàng** (`yeu_cau_mua_hang`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa

### Quản lý kho  ·  phòng Kho

*Nhân sự & Lương*
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

*Mua hàng*
- **Yêu cầu mua hàng** (`yeu_cau_mua_hang`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa

### Kế toán bán hàng  ·  phòng Kế toán

*Nhân sự & Lương*
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

### Kế toán tổng hợp  ·  phòng Kế toán

*Nhân sự & Lương*
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Lương** (`luong`) — phạm vi *Tất cả*  
  Xem · Thêm · Bảng lương tháng · Xem lương & BHXH · Đổi trạng thái · Xuất file
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

*Mua hàng*
- **Mua hàng** (`thu_mua`) — phạm vi *Tất cả*  
  Xem
- **Nhà cung cấp** (`nha_cung_cap`) — phạm vi *Tất cả*  
  Xem

*Kế toán*
- **Đơn mua hàng (Kế toán)** (`ke_toan`) — phạm vi *Tất cả*  
  Xem
- **Phiếu chi / UNC** (`phieu_chi`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Huỷ · Xuất file
- **Phiếu thu** (`phieu_thu`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Đổi trạng thái · Huỷ · Xuất file
- **Công nợ phải trả** (`cong_no_phai_tra`) — phạm vi *Tất cả*  
  Xem
- **Công nợ phải thu** (`cong_no_phai_thu`) — phạm vi *Tất cả*  
  Xem
- **Báo cáo công nợ** (`bao_cao_cong_no`) — phạm vi *Tất cả*  
  Xem
- **Tài khoản ngân hàng** (`tk_ngan_hang`) — phạm vi *Tất cả*  
  Xem · Sửa

### Kế toán kho  ·  phòng Kế toán

*Nhân sự & Lương*
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

### Nhân viên sản xuất  ·  phòng Sản xuất

*Nhân sự & Lương*
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

*Mua hàng*
- **Yêu cầu mua hàng** (`yeu_cau_mua_hang`) — phạm vi *Của tôi*  
  Xem · Thêm · Sửa

### Quản lý sản xuất  ·  phòng Sản xuất

*Nhân sự & Lương*
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

*Mua hàng*
- **Yêu cầu mua hàng** (`yeu_cau_mua_hang`) — phạm vi *Phòng ban*  
  Xem · Thêm · Sửa

### Nhân viên mua hàng  ·  phòng Mua hàng

*Nhân sự & Lương*
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

*Mua hàng*
- **Yêu cầu mua hàng** (`yeu_cau_mua_hang`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa
- **Mua hàng** (`thu_mua`) — phạm vi *Của tôi*  
  Xem · Thêm · Sửa
- **Nhà cung cấp** (`nha_cung_cap`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa

### Trưởng bộ phận mua hàng  ·  phòng Mua hàng

*Nhân sự & Lương*
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

*Mua hàng*
- **Yêu cầu mua hàng** (`yeu_cau_mua_hang`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá
- **Mua hàng** (`thu_mua`) — phạm vi *Phòng ban*  
  Xem · Thêm · Sửa · Xoá
- **Nhà cung cấp** (`nha_cung_cap`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Xoá

### Quản lý giao hàng  ·  phòng Giao hàng

*Nhân sự & Lương*
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

*Giao hàng*
- **Giao hàng** (`giao_hang`) — phạm vi *Tất cả*  
  Xem · Thêm · Sửa · Lên đơn giao hàng · Nhân viên giao hàng · Huỷ

### Nhân viên giao hàng  ·  phòng Giao hàng

*Nhân sự & Lương*
- **Chấm công** (`cham_cong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nghỉ phép** (`nghi_phep`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Tăng ca** (`tang_ca`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Lương** (`luong`) — phạm vi *Của tôi*  
  Xem · Thêm
- **Nội quy công ty** (`noi_quy`) — phạm vi *Tất cả*  
  Xem

*Giao hàng*
- **Giao hàng** (`giao_hang`) — phạm vi *Của tôi*  
  Xem · Thêm
