# CẨM NANG DOMAIN — NHÀ MÁY IN OFFSET (cho ERP Sao Việt Nhật)

> **Tài liệu domain DUY NHẤT & ĐẦY ĐỦ.** Mô tả toàn bộ một **nhà máy in offset thực tế** — từ
> công nghệ, cơ cấu tổ chức, dây chuyền sản xuất, đến mọi phân hệ quản trị (kho, mua hàng, gia
> công trong/ngoài, giao hàng, HCNS, lương khoán, công nợ, kế toán giá thành) — làm nền thiết kế
> các module ERP.
>
> **Bộ tài liệu nền của repo:** file này thay thế và gộp toàn bộ kiến thức domain (kỹ thuật +
> luồng sản xuất + bản đồ module). Từ điển dữ liệu ở [DB_SCHEMA.md](DB_SCHEMA.md); mối nối chéo
> phân hệ ở [CROSS_MODULE_LINKS.md](CROSS_MODULE_LINKS.md).
>
> **Độ tin cậy nguồn:**
> - **KỸ THUẬT & TIÊU CHUẨN** (ISO 12647, G7, ICC, AM/FM tram, CTP) — nguồn gốc chính thống
>   (ISO.org, color.org/ICC, Idealliance), kiểm chứng đối kháng (deep-research 2026-06-30, 24/25
>   claim xác nhận) → **tin cậy cao**.
> - **THƯƠNG MẠI & VẬN HÀNH NHÀ MÁY VN** (giá ram, khổ giấy, % bù hao, lương khoán, định mức gia
>   công) — bảng giá/blog ngành + tập quán sản xuất → **tham khảo**, đánh dấu `‹cần xác nhận với
>   Sao Việt Nhật›`. **Không hardcode số liệu**; coi là dữ liệu có phiên bản theo thời gian.

---

## MỤC LỤC

- **PHẦN I — CÔNG NGHỆ IN OFFSET**
  - [1. Nguyên lý & so sánh công nghệ](#1-nguyên-lý--so-sánh-công-nghệ)
  - [2. Chế bản / Tiền in (Pre-press)](#2-chế-bản--tiền-in-pre-press)
  - [3. Máy in offset](#3-máy-in-offset)
  - [4. Vật tư: giấy, mực, vật tư gia công](#4-vật-tư-giấy-mực-vật-tư-gia-công)
  - [5. Gia công sau in (thành phẩm)](#5-gia-công-sau-in-thành-phẩm)
  - [6. Kiểm soát chất lượng & tiêu chuẩn màu](#6-kiểm-soát-chất-lượng--tiêu-chuẩn-màu)
- **PHẦN II — NHÀ MÁY & DÂY CHUYỀN SẢN XUẤT**
  - [7. Cơ cấu tổ chức nhà máy in](#7-cơ-cấu-tổ-chức-nhà-máy-in)
  - [8. Quy trình từ yêu cầu khách → giao hàng (14 bước)](#8-quy-trình-từ-yêu-cầu-khách--giao-hàng)
  - [9. Máy trạng thái Job & chứng từ](#9-máy-trạng-thái-job--chứng-từ)
  - [10. Định mức kỹ thuật & bù hao](#10-định-mức-kỹ-thuật--bù-hao)
- **PHẦN III — CÁCH TÍNH GIÁ THÀNH & BÁO GIÁ**
  - [11. Cấu trúc giá thành in offset](#11-cấu-trúc-giá-thành-in-offset)
- **PHẦN IV — CÁC PHÂN HỆ QUẢN TRỊ (MODULE ERP)**
  - [12. Kho (Inventory)](#12-kho-inventory)
  - [13. Mua hàng (Procurement)](#13-mua-hàng-procurement)
  - [14. Gia công — 3 hình thái](#14-gia-công--3-hình-thái)
  - [15. Giao hàng (Delivery)](#15-giao-hàng-delivery)
  - [16. HCNS (Nhân sự – Hành chính)](#16-hcns-nhân-sự--hành-chính)
  - [17. Lương — đặc biệt LƯƠNG KHOÁN](#17-lương--đặc-biệt-lương-khoán)
  - [18. Công nợ phải thu / phải trả](#18-công-nợ-phải-thu--phải-trả)
  - [19. Kế toán – Tài chính & giá thành job](#19-kế-toán--tài-chính--giá-thành-job)
  - [20. Máy móc & Bảo trì (lịch máy)](#20-máy-móc--bảo-trì-lịch-máy)
  - [21. Báo cáo & Dashboard](#21-báo-cáo--dashboard)
- **PHẦN V — HÀM Ý THIẾT KẾ ERP**
  - [22. Bản đồ module & ma trận tích hợp](#22-bản-đồ-module--ma-trận-tích-hợp)
  - [23. Thực thể dữ liệu cốt lõi](#23-thực-thể-dữ-liệu-cốt-lõi)
  - [24. Ánh xạ RBAC (nền sẵn có)](#24-ánh-xạ-rbac-nền-sẵn-có)
- **PHẦN VI — PHỤ LỤC**
  - [25. Glossary Việt–Anh](#25-glossary-việtanh)
  - [26. Cần xác nhận với nhà máy thực tế](#26-cần-xác-nhận-với-nhà-máy-thực-tế)
  - [27. Nguồn tham khảo](#27-nguồn-tham-khảo)
- **PHẦN VII — KẾT QUẢ PHẢN BIỆN ĐA CHUYÊN GIA & QUYẾT ĐỊNH THIẾT KẾ** ⭐
  - [28. Bối cảnh & 6 vùng đồng thuận](#28-bối-cảnh--6-vùng-đồng-thuận)
  - [29. Mô hình 2 lớp: Job (thương mại) vs PrintForm (vật lý) — ghép bài](#29-mô-hình-2-lớp-job-thương-mại-vs-printform-vật-lý--ghép-bài)
  - [30. Giá thành 3 lớp & quy trách nhiệm sự cố (fault_party)](#30-giá-thành-3-lớp--quy-trách-nhiệm-sự-cố-fault_party)
  - [31. Công thức then chốt (số con/khổ, bù hao ngược chuỗi, số pass)](#31-công-thức-then-chốt)
  - [32. In bù vs đơn bổ sung; đổi/hủy đơn theo mốc](#32-in-bù-vs-đơn-bổ-sung-đổihủy-đơn-theo-mốc)
  - [33. Lương khoán: đơn vị theo công đoạn + chia khoán tổ](#33-lương-khoán-đơn-vị-theo-công-đoạn--chia-khoán-tổ)
  - [34. Cardinality bắt buộc & quy ước kỹ thuật](#34-cardinality-bắt-buộc--quy-ước-kỹ-thuật)
  - [35. Lộ trình build (P0/P1/P2) & 2 câu hỏi sống còn](#35-lộ-trình-build-p0p1p2--2-câu-hỏi-sống-còn)
- **PHẦN VIII — CƠ CẤU PHÒNG BAN & BẢN ĐỒ MODULE UI/RBAC** ⭐ (đồng thuận 3 vai × 2 vòng)
  - [36. Cơ cấu phòng ban & kiêm nhiệm (RBAC N-N)](#36-cơ-cấu-phòng-ban--kiêm-nhiệm-rbac-n-n)
  - [37. Bản đồ navbar chốt](#37-bản-đồ-navbar-chốt)
  - [38. Danh sách module_key RBAC & ánh xạ phòng ban](#38-danh-sách-module_key-rbac--ánh-xạ-phòng-ban)
  - [39. 6 quyết định đồng thuận (C1–C6)](#39-6-quyết-định-đồng-thuận-c1c6)
- **PHẦN IX — BỘ KHUNG CUỐI (BẢN LÀM VIỆC — còn chỉnh)** ⭐⭐
  - [40. Ba quyết định lớn (D1–D3)](#40-ba-quyết-định-lớn-d1d3)
  - [41. Bản đồ module (12 nhóm)](#41-bản-đồ-module-12-nhóm)
  - [42. Ánh xạ nghiệp vụ → định khoản (kế toán hybrid)](#42-ánh-xạ-nghiệp-vụ--định-khoản-kế-toán-hybrid)
  - [43. Tham số cấu hình + P0 schema + điểm còn ngỏ](#43-tham-số-cấu-hình--p0-schema--điểm-còn-ngỏ)

---

# PHẦN I — CÔNG NGHỆ IN OFFSET

## 1. Nguyên lý & so sánh công nghệ

In offset (**offset lithography**) in theo nguyên lý **đẩy nhau dầu–nước** (oil–water repulsion):
vùng có hình ăn mực/kỵ nước, vùng trắng bắt nước/kỵ mực. Hình **truyền gián tiếp**:

```
   bản kẽm (plate)  →  tấm cao su offset (blanket)  →  giấy (substrate)
```

"Bản kẽm" (zinc) là tên gọi truyền thống VN; bản hiện đại là **nhôm phủ (aluminum)**. Ưu điểm:
chất lượng cao, ổn định, **đơn giá rẻ khi in số lượng lớn**; nhược: phí cố định ban đầu cao (kẽm +
canh máy) nên không kinh tế với số lượng ít. [azoka.vn; en.wikipedia/Offset_printing; prepressure.com]

| Công nghệ | Cơ chế | Chuẩn | Phù hợp |
|---|---|---|---|
| **Offset** | Bản → blanket → giấy | ISO 12647-2 | Số lượng lớn, chất lượng cao |
| **Digital (KTS)** | Toner/phun trực tiếp, không bản | ISO 12647-7/8 | Số lượng ít, in nhanh, dữ liệu biến đổi |
| **Flexo** | Bản nổi mềm, mực lỏng | ISO 12647-6 | Bao bì, nhãn cuộn, carton |
| **Ống đồng (gravure)** | Bản lõm khắc trục đồng | — | Sản lượng cực lớn, màng mềm |

## 2. Chế bản / Tiền in (Pre-press)

Chuỗi: **thiết kế → bình bản (imposition) → tách màu → RIP → CTP → bản kẽm**.

- **Màu & độ phân giải:** chế độ **CMYK**, ảnh **≥300 dpi**, 4 bản tách màu; màu pha (spot/Pantone)
  là **bản riêng** ngoài CMYK. [azoka.vn]
- **Bình bản (imposition):** sắp nhiều sản phẩm/trang lên 1 khổ in → quyết định **"số con trên
  khổ"** (pieces-per-sheet) — biến chốt của giá. Cần tính **chừa xén, nhíp (gripper), bleed, canh
  thớ giấy (grain)**.
- **RIP (Raster Image Processor):** rasterize thành **tram (halftone)**, định hình điểm/góc tram,
  xuất **≥2.400 dpi**. [cnctpplates.com; Fujifilm]
- **CTP (Computer-to-Plate):** laser ghi trực tiếp lên bản nhôm phủ, **bỏ phim**. Số bản =
  **số màu × số mặt**.
- **Tram:** **AM** (lưới đều, điểm to-nhỏ 10–200 µm, cần 4 góc tram) vs **FM/stochastic** (điểm
  ~25 µm rải ngẫu nhiên, **triệt moiré/rosette**). [en.wikipedia/Stochastic_screening; printwiki]
- **ICC profile + Proofing:** quản lý màu xuyên thiết bị; **bản in thử (proof)** để khách **duyệt
  mẫu** trước khi in chính thức.

## 3. Máy in offset

- **Tờ rời (sheet-fed)** vs **cuộn (web):** tờ rời linh hoạt, chất lượng cao (catalogue, hộp);
  cuộn tốc độ cao (báo, tạp chí số lượng cực lớn).
- **Số đơn vị in (units) = số màu in 1 lượt** (máy 4 màu in CMYK 1 lượt).
- **Khổ máy:** quy theo số trang bình (4/8/16 trang…), gắn khổ giấy chạy được.
- **Trở nhật / trở lật (work-and-turn / -tumble):** kỹ thuật in 2 mặt bằng cách trở tờ giấy.
- **Tốc độ:** ~80–120 tờ/phút (máy phổ thông VN) đến **300+ tờ/phút** (máy hiện đại) → ảnh hưởng
  lịch máy & công in. [inmedia.vn]

## 4. Vật tư: giấy, mực, vật tư gia công

### Định lượng & khổ giấy
- **Định lượng (gsm)** = g/m² (ISO 536), `gsm = khối lượng(g)/diện tích(m²)`; bán theo **bước rời
  rạc**. [vprintpack.com.vn]
- ⚠️ **Khổ giấy VN KHÔNG dùng ISO A/B** — dùng **khổ cm**, viết **cạnh ngắn trước**:

  | Khổ (cm) | Ghi chú |
  |---|---|
  | **65×86** | Phổ biến nhất (sách, ấn phẩm) |
  | **79×109** | Offset công nghiệp khổ lớn |
  | 60×84, 65×97, 65×100, 84×120 | Khổ lớn khác |
  | 43×65, 54×79, 65×84, 72×102 | Biến thể vùng / khổ cắt |

- Giấy **bán theo ram (~500 tờ)**, **giá theo ram VÀ kg**. Không có 1 list "chuẩn" tuyệt đối (biến
  thể theo vùng/NCC). [bảng giá Thanh Huyền; intietkiem.com]

### 5 họ giấy lõi tại VN

| Họ giấy | gsm tham khảo | Dùng cho |
|---|---|---|
| **Ford / Fort** (không tráng) | ~58–250 | Ruột sách, tiêu đề thư, vở |
| **Couche** (tráng 2 mặt: bóng/mờ) | ~90–300 | Tờ rơi, catalogue, poster, brochure |
| **Ivory** (tráng 1 mặt) | ~190–400 | Hộp giấy mặt trắng |
| **Bristol** (cứng, mịn 2 mặt) | ~190–400 | Name card, bìa, hộp |
| **Duplex** (mặt trắng/mặt xám) | ~180–**500** | Hộp giấy bồi |

> Đính chính kiểm chứng: **Duplex tới 500 gsm** (không phải 400). Ngoài 5 họ còn Kraft, Crystal,
> art paper… Khoảng gsm là tồn của *một* NCC, không phổ quát. [bảng giá Thanh Huyền; inhiflex.vn]

### Mực & hóa chất
- **Mực:** CMYK + **màu pha (spot)** — nhà máy thường có **bộ phận pha mực** với **công thức pha**
  (ink recipe) lưu lại để tái lặp; quản lý **kho mực pha**.
- **Dung dịch làm ẩm (nước máng / fountain solution)** — cốt lõi nguyên lý dầu–nước.
- Hóa chất phụ: dung môi vệ sinh, keo, phụ gia, cồn.
- **Vật tư gia công:** màng cán (bóng/mờ), nhũ/foil ép kim, keo (đóng cuốn), **khuôn bế (die)** —
  khuôn bế thường **lưu lại để tái bản**.

## 5. Gia công sau in (thành phẩm)

| Công đoạn (VN) | English | Mô tả |
|---|---|---|
| Cán màng (bóng/mờ) | Lamination | Phủ màng nhựa bảo vệ |
| Cấn bế | Die-cut | Cắt theo khuôn (hộp, tem) |
| Bồi | Mounting | Dán giấy in lên nền dày |
| Ép kim/nhũ | Hot foil stamping | Ép lớp ánh kim |
| Dập nổi/chìm | Emboss/deboss | Tạo hình nổi/chìm |
| UV định hình | Spot UV | Phủ UV bóng cục bộ |
| Đóng cuốn — keo nhiệt | Perfect binding | Dán gáy keo (sách dày) |
| Đóng cuốn — đóng kim | Saddle stitch | Bấm kim gáy (sách mỏng) |
| Đóng cuốn — khâu chỉ | Sewn binding | Khâu chỉ (cao cấp) |
| Gấp / Xén | Folding / Trimming | Gấp & cắt thành phẩm |

> Nhiều công đoạn (đặc biệt **bế, cán, ép kim**) thường **thuê ngoài** → xem [§14](#14-gia-công--3-hình-thái).

## 6. Kiểm soát chất lượng & tiêu chuẩn màu

- **ISO 12647-2** = chuẩn kiểm soát quá trình in offset: ΔE (sai màu), mật độ mực (ink density),
  gia tăng tầng thứ (tone value/dot gain), cân bằng xám (grey balance). Bản hiện hành **2013**.
  Series: part 2 offset, part 3 coldset newsprint, part 6 flexo, part 7 digital proof.
  [color.org/ICC; iso.org]
- **G7** = hiệu chỉnh **theo so màu/cân bằng xám** (colorimetric, **không phải dot-gain/TVI**),
  chuẩn hóa CGATS TR015; tông qua **NPDC (Neutral Print Density Curves)** + cân bằng xám CIELAB
  a*/b*; "hài hòa với ISO 12647"; GRACoL 2006 ≈ FOGRA 39 (nay FOGRA 51/52).
  [en.wikipedia/G7_Method; Techkon G7 Guide; Idealliance]
- Vận hành QC: **chồng màu (registration)**, đo **mật độ mực**, đối chiếu **proof đã duyệt**, KCS
  thành phẩm. Nhiều nhà in vận hành theo **ISO 9001** ‹cần xác nhận SVN có chứng nhận không›.

---

# PHẦN II — NHÀ MÁY & DÂY CHUYỀN SẢN XUẤT

## 7. Cơ cấu tổ chức nhà máy in

Cơ cấu điển hình (ánh xạ phòng ban — đã có nền RBAC departments/roles):

| Khối | Phòng / Bộ phận | Vai trò |
|---|---|---|
| Kinh doanh | **Phòng Kinh doanh / CSKH** | Nhận đơn, báo giá, chăm sóc khách, công nợ phải thu |
| Thiết kế–Kỹ thuật | **Phòng Thiết kế / Chế bản (Pre-press)** | Thiết kế, dàn trang, bình bản, xuất file, **CTP**, pha mực |
| Điều hành SX | **Điều độ sản xuất (PPC)** | Kế hoạch, **lệnh sản xuất**, **lịch máy** |
| Sản xuất | **Xưởng in** (tổ máy offset, tổ KTS) | In |
| Sản xuất | **Xưởng thành phẩm** (cán/bế/ép/gấp/đóng cuốn/xén) | Gia công sau in |
| Chất lượng | **KCS / QC** | Kiểm tra chất lượng & số lượng |
| Cung ứng | **Kho** + **Phòng Vật tư/Mua hàng** | Nhập–xuất–tồn, mua giấy/mực/vật tư |
| Hỗ trợ | **Kế toán – Tài chính** | Thu/chi, hóa đơn, giá thành, công nợ |
| Hỗ trợ | **HCNS** | Nhân sự, chấm công, lương, BHXH |
| Quản trị | **Ban Giám đốc** | Duyệt, báo cáo |

- Nhà in thường chạy **2–3 ca/ngày** → cần quản lý **ca/kíp** (ảnh hưởng chấm công, lịch máy, phụ
  cấp ca đêm). ‹cần xác nhận số ca của SVN›
- Yếu tố **an toàn lao động & môi trường:** xử lý dung môi/hóa chất, phụ cấp độc hại.

## 8. Quy trình từ yêu cầu khách → giao hàng

```
①  TIẾP NHẬN YÊU CẦU            (KD) — brief: SP, số lượng, khổ, số màu, gia công, deadline, file
②  KHẢO SÁT & TƯ VẤN KỸ THUẬT  (KD + Chế bản) — chọn khổ, số con/khổ, máy, số bản
③  BÁO GIÁ                      (KD) ──► duyệt giá? ──No──► sửa/đàm phán (lặp ②③)
④  CHỐT ĐƠN / HỢP ĐỒNG          (KD + KT) — PO, đặt cọc, (ứng giấy)
⑤  NHẬN FILE & DUYỆT MẪU        (Chế bản + KH) ──► KÝ DUYỆT? ──No──► sửa file (lặp)
        ★ CỔNG CHẶN: không chế bản/in khi chưa ký duyệt mẫu
⑥  LỆNH SẢN XUẤT (job ticket)   (Điều độ) — định mức, công đoạn, máy, deadline
⑦  CHẾ BẢN (CTP)                (Chế bản) — xuất bản kẽm
⑧  XUẤT VẬT TƯ                  (Kho) — giấy + mực theo định mức + bù hao
⑨  IN                           (Tổ in) — canh máy → in thử → DUYỆT TỜ ĐẦU → chạy sản lượng
⑩  GIA CÔNG SAU IN              (Thành phẩm / thuê ngoài) — cán, bế, ép, gấp, đóng cuốn, xén
⑪  KCS                          (QC) ──► đạt SL & chất lượng? ──No──► in bù / xử lý lỗi
⑫  ĐÓNG GÓI & GIAO HÀNG         (Kho/Giao nhận) — phiếu giao hàng (POD)
⑬  NGHIỆM THU & CÔNG NỢ         (Kế toán) — hóa đơn, thu phần còn lại
⑭  ĐÓNG JOB & QUYẾT TOÁN        (Kế toán + QL) — giá thành THỰC vs BÁO GIÁ; lưu hồ sơ tái bản
```

**Hai cổng chặn cứng (gate) không được vượt:**
1. **③→④:** chưa **duyệt giá** (+ cọc) → chưa mở sản xuất.
2. **⑤→⑥:** chưa **ký duyệt mẫu** → chưa chế bản/in. *In khi chưa duyệt = rủi ro đắt nhất (mất
   giấy + công + kẽm).*

**Vòng lặp:** ②↔③ (đàm phán giá), trong ⑤ (sửa file đến khi duyệt), ⑪→⑨ (in bù khi thiếu).

### Chi tiết mỗi bước (tác nhân · đầu vào · đầu ra · dữ liệu · rủi ro)

- **① Tiếp nhận yêu cầu** — *KD.* Thu brief đầy đủ: loại SP (catalogue, brochure, tem/nhãn, hộp
  giấy, sách, tờ rơi, name card…), **số lượng**, kích thước (mm, bleed), **giấy** (họ+gsm), **số
  màu**/mặt, **gia công**, deadline, đã có file chưa. → `Customer`, `Inquiry`. *Rủi ro: brief thiếu
  → báo giá sai. 3 biến chốt giá = số lượng × số màu × gia công.*
- **② Khảo sát kỹ thuật** — *KD + Chế bản.* Khả thi? Chọn **khổ giấy tối ưu + số con/khổ**, máy,
  số bản = số màu×số mặt. → `ProductionSpec`. *Rủi ro: sai số con/khổ → sai toàn bộ chi phí.*
- **③ Báo giá** — *KD.* Tính giá (xem [§11](#11-cấu-trúc-giá-thành-in-offset)) theo **bậc số
  lượng**. → `Quotation` (trạng thái draft→sent→approved/rejected/expired, có **hạn hiệu lực** &
  **version**). *Rủi ro: giá giấy cũ → lỗ → time-versioned.*
- **④ Chốt đơn** — *KD + Kế toán.* Hợp đồng/SO, **cọc** ‹%?›, **ứng giấy** nếu khách tự cung. →
  `Order`, `Payment(deposit)`, `PaperAdvance`.
- **⑤ Nhận file & duyệt mẫu** ★ — *Chế bản + KH.* **Preflight** (CMYK, ≥300dpi, font, bleed) →
  bình bản → **proof** (mềm/cứng) → **khách ký duyệt**. → `ProofVersion`. *Cổng chặn cứng.*
- **⑥ Lệnh sản xuất** — *Điều độ.* `JobTicket` + `JobOperation[]` (mỗi công đoạn: máy/tổ, định mức,
  nội bộ/thuê ngoài, trạng thái) + **phân máy/lịch máy**. *Rủi ro: lịch chồng → trễ.*
- **⑦ Chế bản CTP** — *Chế bản.* Ghi **bản kẽm** (số màu×số mặt). Ghi số bản thực (chi phí cố định).
- **⑧ Xuất vật tư** — *Kho.* Xuất giấy (=SL/số con/khổ + bù hao) + mực theo định mức; trừ tồn. →
  `StockIssue`. *Thiếu tồn → mua bổ sung trước.*
- **⑨ In** — *Tổ in.* **Canh máy (makeready)** → **duyệt tờ in đầu (OK sheet)** khớp mẫu → chạy
  sản lượng → ghi **số tờ thực, hao hụt thực, giờ máy**. In 2 mặt qua trở nhật/lật.
- **⑩ Gia công** — *Thành phẩm/thuê ngoài.* Theo phiếu SX (xem [§14](#14-gia-công--3-hình-thái)).
- **⑪ KCS** — *QC.* Kiểm chất lượng + **đếm số đạt**; thiếu → **in bù**. → `QCResult`.
- **⑫ Giao hàng** — *Kho/Giao nhận.* Đóng gói, **phiếu giao hàng ký nhận (POD)**, giao 1 hay nhiều
  đợt. → `Delivery`.
- **⑬ Nghiệm thu & công nợ** — *Kế toán.* Khách nghiệm thu → **hóa đơn** → thu phần còn lại → ghi
  **công nợ**. → `Invoice`, `Payment`, `Receivable`.
- **⑭ Đóng job & quyết toán** — *Kế toán + QL.* So **giá thành thực vs báo giá** → lãi/lỗ job;
  **tính lương khoán** công đoạn; **lưu file/kẽm/khuôn bế** cho **tái bản**.

## 9. Máy trạng thái Job & chứng từ

```
inquiry → quoting → quoted → (rejected | expired)
                      │ approved (+cọc)
                   ordered → proofing → proof_approved        ★ gate
                                          │
                                   in_production
                                   (platemaking → material_issued
                                    → printing → finishing → qc)
                                          │ qc_pass
                                      ready_to_ship → delivered
                                          │
                                      invoiced → paid → closed
```

**Chứng từ theo dòng chảy:** Inquiry → Phương án KT → **Báo giá** → **Đơn hàng/HĐ** → Phiếu thu
cọc/ứng giấy → **Mẫu duyệt** → **Phiếu sản xuất** → Phiếu xuất kho → Phiếu giao/nhận gia công ngoài
→ Biên bản KCS → **Phiếu giao hàng** → **Hóa đơn + phiếu thu** → Báo cáo quyết toán job.

> Mỗi chuyển trạng thái quan trọng nên **ghi audit log** (hạ tầng audit đã có).

## 10. Định mức kỹ thuật & bù hao

Nhà máy vận hành theo **định mức (norms)** — cơ sở để vừa tính giá vừa kiểm soát hao phí:

- **Định mức giấy:** số tờ = (SL thành phẩm ÷ số con/khổ) + **bù hao**.
- **Định mức mực:** g mực / 1.000 tờ / màu (tùy độ phủ — coverage). ‹định mức thực cần lấy từ SVN›
- **Định mức bù hao (giấy bù hao / waste):**
  - **Bù hao chế bản** (hỏng file/bản).
  - **Bù hao in** = makeready (canh máy, ~100 tờ/mặt hoặc >10 tờ canh chồng màu) + running waste.
  - **Bù hao gia công** (cán/bế/xén hỏng).
  - Tổng thường **~3–10%** (hay 3–5%) tùy số lượng, số màu, độ khó. [inmedia.vn; Dataline]
- **Định mức gia công:** thời gian/đơn giá mỗi công đoạn (cán theo m², bế theo nghìn sản phẩm…).
  ‹cần lấy định mức thực từ SVN›
- **Định mức nhân công:** sản lượng/giờ mỗi công đoạn → cơ sở **lương khoán** ([§17](#17-lương--đặc-biệt-lương-khoán)).

> **Quy tắc ERP:** định mức & bù hao là **dữ liệu cấu hình có phiên bản**, dùng cho **báo giá**
> (dự kiến) và đối chiếu **thực tế** lúc quyết toán → **vòng lặp hiệu chỉnh định mức**.

---

# PHẦN III — CÁCH TÍNH GIÁ THÀNH & BÁO GIÁ

## 11. Cấu trúc giá thành in offset

```
GIÁ THÀNH = NVL trực tiếp (GIẤY + MỰC + vật tư GC)
          + Chi phí CHẾ BẢN (KẼM/bản)
          + CÔNG IN (lượt in = số màu × số tờ)
          + GIA CÔNG (nội bộ + thuê ngoài)
          + Nhân công trực tiếp (lương khoán)
          + Chi phí SX chung (khấu hao máy, điện, quản lý phân xưởng)
GIÁ BÁN  = Giá thành + lợi nhuận (− chiết khấu sản lượng/khách VIP)
```

**Các đại lượng tính:**
- **Số con trên khổ** (từ bình bản) — biến chốt.
- **Số tờ in** = `(Số lượng ÷ số con/khổ) + bù hao`.
- **Số bản kẽm** = **số màu × số mặt** ⚠️ **BIẾN — KHÔNG cố định 4**.
  > Claim *"mỗi job luôn 1 bộ 4 bản CMYK cố định"* đã **bị kiểm chứng bác bỏ (0–3)**. Job 1 màu →
  > 1 bản; 4 màu 2 mặt → 8 bản; có màu pha → thêm bản. **Mô hình hóa số bản là biến.**
- **Lượt in (công in)** = `số màu × số tờ in`.
- **Chi phí giấy** = số tờ × đơn giá (quy từ ram/kg, theo **bảng giá time-versioned**).

**Tại sao in càng nhiều càng rẻ:** chi phí **cố định/job** (kẽm, canh máy, bù hao set-up) **không
đổi theo số lượng** → chia trên nhiều đơn vị → đơn giá giảm. Đơn nhỏ gánh toàn bộ phí cố định → có
**mức tối thiểu (~1.000 lượt in)**. Đây là cơ sở **chiết khấu theo sản lượng**. [inmedia.vn;
treebox.vn; uprint.vn; Dataline MultiPress] *(Giấy là chi phí biến đổi; bậc giảm giá có điểm bão hòa.)*

> **Đặc thù kế toán:** nhà in dùng **giá thành theo đơn hàng (job-order costing)** — mỗi job một
> giá thành riêng, không phải process costing.

---

# PHẦN IV — CÁC PHÂN HỆ QUẢN TRỊ (MODULE ERP)

## 12. Kho (Inventory)

- **Mục đích:** Nhập–xuất–tồn vật tư & thành phẩm, **truy vết theo job**, cơ sở giá thành.
- **Đặc thù in:**
  - **Giấy** theo **họ × gsm × khổ (cm)**; tồn theo **tờ / ram / kg** (quy đổi được); có thể theo
    **lô** (độ trắng/ẩm khác nhau).
  - **Mực** theo màu (CMYK + pha); **kho mực pha** + công thức pha.
  - **Vật tư gia công:** màng, keo, nhũ, **bản kẽm**, **khuôn bế** (lưu cho tái bản).
  - Nhiều kho: **giấy · mực/vật tư · bán thành phẩm (tờ in chờ gia công) · thành phẩm · hàng đi/về
    gia công ngoài**.
- **Thực thể:** `Warehouse`, `Material`, `PaperMaster`(họ×gsm×khổ), `StockLot`, `StockMove`
  (nhập/xuất/chuyển/kiểm kê), `StockBalance`.
- **Quy tắc:** tồn **min/max** → cảnh báo mua; **giá vốn** (bình quân gia quyền/FIFO ‹xác nhận›);
  **mỗi xuất kho gắn job**; kiểm kê định kỳ điều chỉnh chênh lệch.
- **Tích hợp:** ← Mua hàng; → Sản xuất (xuất VT §⑧); → Kế toán (giá vốn, giá trị tồn).

## 13. Mua hàng (Procurement)

- **Luồng:** `Đề nghị mua (PR) → Đơn mua (PO) → Nhận hàng (GR, có thể nhiều đợt) → Hóa đơn NCC →
  Công nợ phải trả`. Nguồn PR: **thiếu tồn (min/max)** hoặc **mua theo job**.
- **Đặc thù in:**
  - **Mua giấy theo job** rất phổ biến (giấy đặc chủng không trữ) → PO link job.
  - **Ứng giấy của khách:** khách tự cung giấy → nhập kho dạng **"vật tư của khách"** (không tính
    tiền giấy, chỉ tính công in/gia công) — **phân biệt rõ** với giấy nhà in mua. ⚠️ ảnh hưởng giá thành.
  - Giá NCC biến động → **bảng giá NCC time-versioned**.
- **Thực thể:** `Supplier` (vật tư & gia công), `PurchaseRequest`, `PurchaseOrder`, `GoodsReceipt`,
  `SupplierInvoice`, `SupplierPriceList`(versioned).
- **Tích hợp:** → Kho; → Công nợ phải trả; ← Sản xuất/Kho (nhu cầu).

## 14. Gia công — 3 hình thái

> Một job có thể **trộn cả 3** cho các công đoạn khác nhau, hoặc **toàn bộ** đặt ngoài. ERP mô hình:
> mỗi `JobOperation.execution_mode ∈ {internal, outsourced}`; mỗi `Job.production_mode ∈ {in_house,
> mixed, full_outsource}`.

### 14A. Gia công TRONG nhà máy (in-house)
- Dùng máy & nhân công nhà in (cán, bế, gấp, xén, đóng cuốn…).
- Chi phí = vật tư GC (xuất kho) + **công lao động (lương khoán công đoạn)** + giờ máy.
- `JobOperation(type=internal, work_center, định mức, sản lượng thực, tổ/NV)`.
- Tích hợp: → Kho (xuất VT); → Lương (sản lượng → khoán); → Máy móc (giờ máy).

### 14B. Gia công MỘT PHẦN ngoài (partial outsourcing)
- **Một số công đoạn** gửi xưởng ngoài (vd cán+ép kim), phần còn lại nội bộ.
- **Phiếu xuất gia công** (giao bán thành phẩm) → **Phiếu nhập sau gia công** (nhận về + **hao hụt
  tại xưởng ngoài**). **Đơn giá GC** theo SP/kg/tờ/m².
- **Đối soát** số giao↔nhận; **công nợ phải trả NCC gia công**.
- Rủi ro: mất mát/hao hụt ngoài, trễ tiến độ, chất lượng.
- `JobOperation(type=outsourced_partial)`, `OutsourceOrder`(NCC, đơn giá, giao/nhận, hao hụt, đối
  soát), `StockMove(đi/về)`.

### 14C. Gia công TOÀN BỘ ngoài ("đặt in" / môi giới — broker/trading)
- Nhà in **nhận đơn khách nhưng KHÔNG tự sản xuất** — **đặt toàn bộ** ở nhà in/xưởng khác rồi giao
  lại khách. **Không qua công đoạn nội bộ.**
- **Liên kết đơn bán (khách) ↔ đơn đặt sản xuất (NCC)** trên cùng job; **lãi = giá bán − giá đặt**.
- Vẫn cần **KCS hàng nhận về** + **giao hàng** + **công nợ 2 đầu**.
- `Job(production_mode=full_outsource)`, `OutsourceOrder(full)` link `Order`(bán)↔`Supplier`(in);
  bỏ qua chế bản/in/định mức nội bộ; chi phí chính = **giá mua dịch vụ in trọn gói**.

## 15. Giao hàng (Delivery)

- **Giao nhiều đợt (partial delivery)** với đơn lớn; nhiều địa điểm; vận chuyển **nội bộ/thuê**
  (phí ship vào chi phí job ‹ai chịu?›).
- Thành phẩm đạt KCS → phiếu giao → vận chuyển → **ký nhận (POD)** → cập nhật đã giao/còn lại; hỗ
  trợ **đổi/trả** nếu lỗi.
- **Thực thể:** `Delivery`(đợt, SL, ngày, POD), `Shipment`/`Carrier`, `DeliveryNote`.
- Tích hợp: ← Sản xuất; → Công nợ (đủ điều kiện hóa đơn); → Kho (giảm tồn TP).

## 16. HCNS (Nhân sự – Hành chính)

- **Hồ sơ nhân viên**, **hợp đồng lao động**, chức danh, tổ/phòng (nền RBAC đã có).
- **Chấm công:** **ca/kíp** (nhà in 2–3 ca), máy chấm công, **tăng ca (OT)**, đi muộn.
- **Nghỉ phép** (năm/ốm/không lương); **bảo hiểm** (BHXH/BHYT/BHTN); **thuế TNCN**; **công đoàn**.
- Phụ cấp **ca đêm**, **độc hại** (hóa chất in); khen thưởng/kỷ luật.
- **Thực thể:** `Employee`, `LaborContract`, `Shift`, `Attendance`, `LeaveRequest`, `Insurance`.
- Tích hợp: → Lương; ↔ RBAC; → Sản xuất (tổ/NV thực hiện công đoạn).

## 17. Lương — đặc biệt LƯƠNG KHOÁN

> Vùng đặc thù nhất của xí nghiệp in; thường **trộn nhiều hình thức** trong cùng bảng lương.

- **Hình thức lương:**
  1. **Lương thời gian** (tháng/ngày/giờ) — gián tiếp, văn phòng, quản lý.
  2. **Lương khoán sản phẩm/công đoạn (piecework)** — công nhân SX: theo **sản lượng thực mỗi công
     đoạn × đơn giá khoán**. Nguồn = **sản lượng từ `JobOperation`** (số đạt KCS).
  3. **Khoán theo tổ/nhóm** rồi **chia nội bộ** theo công/điểm/hệ số.
  4. **Khoán theo job** (trọn gói đầu việc) chia cho người tham gia.
  5. Kết hợp: cơ bản + khoán + **thưởng năng suất** + phụ cấp (ca đêm/độc hại) + OT.
- **Công thức khoán:**
  ```
  Lương khoán NV = Σ ( sản lượng đạt của NV ở công đoạn i × đơn giá khoán công đoạn i )
  ```
  cần **bảng đơn giá khoán** theo **công đoạn × loại SP** (versioned) + **bảng kê sản lượng** theo
  NV/tổ theo job/công đoạn.
- **Thực thể:** `WageScheme`(time/piece/job), `PieceRate`(công đoạn×SP, versioned),
  `OutputRecord`(NV × công đoạn × job × số lượng đạt), `PayrollPeriod`, `Payslip`.
- **Luồng:** Chấm công ([§16](#16-hcns-nhân-sự--hành-chính)) + Sản lượng công đoạn ([§8](#8-quy-trình-từ-yêu-cầu-khách--giao-hàng)/[§14](#14-gia-công--3-hình-thái))
  → tính lương kỳ → phiếu lương → chi/Kế toán → **nhân công trực tiếp vào giá thành job**.
- ‹**Cần khảo sát SVN:** khoán cá nhân hay tổ; đơn giá khoán theo công đoạn nào; quy đổi "công"/điểm;
  thưởng năng suất; phụ cấp ca/độc hại.›

## 18. Công nợ phải thu / phải trả

- **Phải thu (AR — khách):** đơn hàng/giao hàng → hóa đơn → thu (trừ cọc). Theo dõi **tuổi nợ**,
  **hạn mức tín dụng**, **nhắc nợ**.
- **Phải trả (AP — NCC):** NCC **vật tư** (giấy/mực) + NCC **gia công ngoài** + vận chuyển → lịch
  trả → chi.
- **Thực thể:** `Receivable`, `Payable`, `PaymentSchedule`, `AgingBucket`, `CreditLimit`.
- Tích hợp: ← Bán hàng/Giao hàng (AR); ← Mua hàng/Gia công ngoài (AP); → Kế toán.

## 19. Kế toán – Tài chính & giá thành job

- **Phạm vi:** phiếu thu/chi, sổ quỹ, ngân hàng, **hóa đơn VAT** (đầu ra/đầu vào), **giá thành theo
  job** (tập hợp giấy+mực+kẽm+công in+gia công+nhân công+SX chung), **lãi/lỗ theo job/khách/kỳ**.
- **Đặc thù:** **job-order costing** + đối chiếu **thực vs báo giá** (§14 bước ⑭).
- **Thực thể:** `CashVoucher`, `BankTxn`, `VatInvoice`, `JobCost`(estimated vs actual), `LedgerEntry`.
- ‹Cần xác nhận: tích hợp phần mềm kế toán hiện hữu (MISA/FAST…) hay làm trong ERP; quy tắc VAT/TNCN/BHXH.›

## 20. Máy móc & Bảo trì (lịch máy)

- Danh mục máy (khổ, số màu, tốc độ, trở nhật/lật), **lịch máy (scheduling)** theo deadline, thời
  gian **makeready**, **bảo trì định kỳ/sự cố** (downtime ảnh hưởng tiến độ).
- **Thực thể:** `Machine`, `MachineSchedule`, `MaintenancePlan`, `Downtime`.
- Tích hợp: ← Sản xuất (lệnh SX cần máy); → Báo cáo (hiệu suất máy — OEE).
- ‹Cần xác nhận: đội máy thực tế SVN.›

## 21. Báo cáo & Dashboard

- **Bán hàng:** doanh thu theo khách/SP/kỳ; tỷ lệ báo giá→chốt đơn.
- **Sản xuất:** tiến độ job; **hiệu suất máy**; **bù hao thực vs định mức**.
- **Tài chính:** **lãi/lỗ theo job** (thực vs báo giá); công nợ phải thu/phải trả + tuổi nợ.
- **Kho:** tồn giấy/mực; cảnh báo dưới min; vòng quay tồn.
- **Nhân sự/lương:** năng suất công đoạn; quỹ lương.

---

# PHẦN V — HÀM Ý THIẾT KẾ ERP

## 22. Bản đồ module & ma trận tích hợp

| # | Module | Mục | Ưu tiên |
|---|---|---|---|
| M1 | Bán hàng/CRM + **Báo giá** | §8①–④, §11 | ★★★ |
| M2 | **Sản xuất** (Job, chế bản, in, KCS) | §8⑤–⑪ | ★★★ |
| M3 | **Kho** | §12 | ★★★ |
| M4 | **Mua hàng** | §13 | ★★★ |
| M5 | **Gia công** (3 hình thái) | §14 | ★★★ |
| M6 | **Giao hàng** | §15 | ★★ |
| M7 | **HCNS** | §16 | ★★ |
| M8 | **Lương** (khoán) | §17 | ★★★ |
| M9 | **Công nợ** (AR/AP) | §18 | ★★★ |
| M10 | **Kế toán** + giá thành | §19 | ★★ |
| M11 | **Máy móc & lịch máy** | §20 | ★★ |
| M12 | **Báo cáo/Dashboard** | §21 | ★★ |
| — | Auth + RBAC + Audit | spec-01..05 | **ĐÃ CÓ** |

**Ma trận tích hợp (ai cấp dữ liệu cho ai):**

| ▼ cấp ► | Kho | Mua | SX/Job | GC ngoài | Lương | Công nợ | Kế toán |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Bán hàng/Báo giá | | | ✔ mở job | | | ✔ AR | ✔ |
| Mua hàng | ✔ nhập | | | | | ✔ AP | ✔ |
| Kho | | ✔ cảnh báo | ✔ xuất VT | ✔ xuất/nhập BTP | | | ✔ giá vốn |
| Sản xuất/Job | ✔ nhu cầu | ✔ theo job | | ✔ CĐ ngoài | ✔ sản lượng | | ✔ giá thành |
| Gia công ngoài | ✔ đi/về | | ✔ chuỗi CĐ | | | ✔ AP | ✔ |
| HCNS | | | ✔ nhân công | | ✔ chấm công | | |
| Lương | | | | | | | ✔ chi lương |

## 23. Thực thể dữ liệu cốt lõi

| Thực thể | Ghi chú thiết kế |
|---|---|
| **Customer** | Mở rộng từ nền RBAC; công nợ, hạn mức |
| **PrintProduct** | Loại SP + kích thước thành phẩm (bleed/trim) |
| **PaperMaster** | Khóa **họ × gsm × khổ (cm)**; giá **per-ram & per-kg**, **time-versioned** |
| **Material/Ink + BOM + Định mức** | Mực (+công thức pha), vật tư GC, **norms** tiêu hao |
| **Plate/Impression** | `số bản = số màu × số mặt` (BIẾN); `lượt in = số màu × số tờ` |
| **WasteRule** | Bù hao theo **% hoặc tờ/mặt**, cấu hình theo SP/máy |
| **Machine + Schedule** | Khổ, số màu, trở nhật/lật, makeready → **lịch máy** |
| **Quotation** | Engine: số con/khổ → số tờ + bù hao → giấy+kẽm+công in+gia công → **đơn giá theo bậc SL** |
| **Job / JobTicket** | `production_mode ∈ {in_house, mixed, full_outsource}`; vòng đời §9 |
| **JobOperation** | `execution_mode ∈ {internal, outsourced}`; sản lượng thực, tổ/NV, máy |
| **OutsourceOrder** | Gia công ngoài (một phần/toàn bộ): NCC, đơn giá, giao/nhận, hao hụt, đối soát |
| **Inventory (Warehouse/StockMove/Lot)** | Giấy tờ⇄ram⇄kg; nhiều kho; truy vết job |
| **Supplier + PurchaseOrder + GoodsReceipt** | NCC vật tư & gia công; mua theo job; giấy của khách |
| **Employee + Attendance + Shift** | HCNS; ca/kíp; OT |
| **WageScheme + PieceRate + OutputRecord + Payslip** | **Lương khoán** theo công đoạn |
| **Receivable / Payable** | Công nợ 2 đầu; tuổi nợ |
| **JobCost (estimated vs actual)** | Quyết toán; vòng lặp hiệu chỉnh định mức |

**4 nguyên tắc kiến trúc (nối layer `routers→services→repositories→DB`):**
1. **Job là trung tâm** — mọi chứng từ/vật tư/tiền/công đoạn **link 1 job** (khác ERP generic).
2. **Logic giá & quyết toán đặt ở `services/`** (`quotation_service`, `costing_service`,
   `payroll_service`) — business logic thuần, tách route & repo.
3. **Giá vật tư, định mức, đơn giá khoán = dữ liệu time-versioned** — không hardcode.
4. **Số bản kẽm là biến** (`số màu × số mặt`); **gia công có 3 hình thái** (internal/partial/full
   outsource) phải mô hình rõ.

## 24. Ánh xạ RBAC (nền sẵn có)

Nền **Auth + RBAC + Audit** (spec-01..05) đủ gán quyền & ghi vết cho toàn bộ module:

| Phòng ban | Module |
|---|---|
| Kinh doanh | M1, AR |
| Chế bản/Kỹ thuật | M2 (file, proof, CTP, pha mực) |
| Điều độ SX | M2 (lệnh SX), M11 (lịch máy) |
| Tổ in / Thành phẩm | M2/M5 |
| QC | M2 (KCS) |
| Kho | M3, M6 |
| Mua hàng | M4, AP |
| HCNS | M7, M8 |
| Kế toán | M9, M10 |
| Ban giám đốc | M12, duyệt |

> Mỗi chuyển trạng thái quan trọng (duyệt giá, duyệt mẫu, xuất kho, đối soát gia công, chi lương)
> → **audit log**.

---

# PHẦN VI — PHỤ LỤC

## 25. Glossary Việt–Anh

| Tiếng Việt | English | Nghĩa |
|---|---|---|
| In offset | Offset lithography | In gián tiếp qua tấm cao su |
| Bản kẽm / kẽm | (Printing) plate | Bản in nhôm phủ |
| Tấm cao su offset | Rubber blanket | Trung gian truyền mực |
| Chế bản / tiền in | Pre-press | Xử lý trước khi in |
| Bình bản | Imposition | Sắp SP/trang lên khổ in |
| Số con trên khổ | Pieces-per-sheet | Số SP trên 1 tờ |
| Tách màu | Color separation | Tách CMYK + spot |
| Tram / góc tram | Halftone / screen angle | Mô phỏng tông bằng điểm |
| CTP | Computer-to-Plate | Ghi bản trực tiếp, bỏ phim |
| RIP | Raster Image Processor | Rasterize ra tram |
| Định lượng | Grammage (gsm) | g/m² |
| Ram | Ream (~500 tờ) | Đơn vị bán giấy |
| Bù hao | Waste / spoilage | Giấy hao set-up/canh máy/GC |
| Công in / lượt in | Impressions | ≈ số màu × số tờ |
| Trở nhật / trở lật | Work-and-turn / -tumble | Kỹ thuật in 2 mặt |
| Tờ rời / cuộn | Sheet-fed / Web | Loại máy offset |
| Pha mực | Ink mixing | Pha màu spot theo công thức |
| Cán màng | Lamination | Phủ màng |
| Cấn bế / khuôn bế | Die-cut / die | Cắt theo khuôn |
| Ép kim/nhũ | Hot foil stamping | Ép ánh kim |
| Dập nổi | Emboss | Tạo hình nổi |
| UV định hình | Spot UV | Phủ UV cục bộ |
| Đóng cuốn (keo/kim/chỉ) | Perfect/Saddle/Sewn binding | Các kiểu đóng gáy |
| Xén | Trimming | Cắt thành phẩm |
| KCS | QC | Kiểm tra chất lượng |
| Phiếu sản xuất / lệnh SX | Job ticket / work order | Lệnh SX 1 job |
| Định mức | Norm / standard consumption | Mức tiêu hao chuẩn |
| Ứng giấy | Paper advance | Khách ứng/tự cung giấy |
| Gia công thuê ngoài | Outsourced finishing | Thuê xưởng ngoài |
| Đặt in (môi giới) | Print brokering / full outsource | Đặt toàn bộ ở xưởng khác |
| Lương khoán | Piecework wage | Trả công theo sản lượng |
| Công nợ phải thu/phải trả | Accounts receivable/payable | Nợ khách / nợ NCC |
| Giá thành theo job | Job-order costing | Mỗi job 1 giá thành |
| Ca / kíp | Shift | Ca làm việc (nhà in 2–3 ca) |

## 26. Cần xác nhận với nhà máy thực tế

Những thứ **không nguồn web nào có** — chỉ Sao Việt Nhật trả lời được, phải khảo sát trước khi build:

1. **Đội máy thực tế:** tờ rời/cuộn, khổ máy tối đa, số đơn vị màu, trở nhật/lật, tốc độ, makeready
   thật → cho lịch máy & công in.
2. **Lương khoán:** khoán cá nhân/tổ; **đơn giá khoán theo công đoạn**; quy đổi "công"/điểm/hệ số;
   thưởng năng suất; phụ cấp ca đêm/độc hại.
3. **Định mức gia công** thực (cán theo m², bế theo nghìn SP, ép kim, đóng cuốn…) + định mức mực.
4. **Tỷ trọng "đặt in" toàn bộ ngoài** vs tự sản xuất; cách quản lý chất lượng & lãi gộp.
5. **Giấy của khách (ứng giấy):** hạch toán khi không tính tiền giấy.
6. **Kế toán/Thuế:** tích hợp phần mềm kế toán hiện hữu hay làm trong ERP; VAT/TNCN/BHXH/công đoàn.
7. **Tái bản (reprint):** giữ kẽm/khuôn bế cũ hay làm lại; quy trình tạo nhanh từ job cũ.
8. **Tổ chức & ca kíp:** số ca/ngày; phòng ban thực tế khớp [§7](#7-cơ-cấu-tổ-chức-nhà-máy-in) không;
   có ISO 9001 không.
9. **Chính sách:** tỷ lệ **đặt cọc**, mốc thanh toán, **hạn mức công nợ**, **chính sách in bù** khi
   KCS thiếu (nhà in chịu hay tính thêm).

> **Khuyến nghị:** lập **bảng khảo sát** cho 9 vùng trên; với (2) lương khoán & (3) định mức gia
> công — đặc thù nhất — nên chạy thêm một đợt **deep-research** + phỏng vấn trực tiếp.

## 27. Nguồn tham khảo

**Kỹ thuật & tiêu chuẩn (gốc/chính thống — tin cậy cao):**
- ICC/ISO — color.org: <https://www.color.org/standardsprofiles.xalter> · ISO catalog: <https://www.iso.org>
- G7: <https://en.wikipedia.org/wiki/G7_Method> · Techkon G7 Guide:
  <https://www.techkonusa.com/wp-content/uploads/2014/05/G7_Guide_Final.pdf> · <https://www.idealliance.org>
- FM/AM tram: <https://en.wikipedia.org/wiki/Stochastic_screening> · <https://printwiki.org/Stochastic_Screening>
- Offset: <https://en.wikipedia.org/wiki/Offset_printing> · <https://www.prepressure.com>
- CTP: <https://cnctpplates.com/what-is-a-ctp-plate-and-how-it-works/> · Fujifilm
- ISO paper sizes: <https://en.wikipedia.org/wiki/International_standard_paper_sizes>

**Thương mại & vận hành VN (blog/bảng giá — tham khảo, không hardcode):**
- Bảng giá giấy Thanh Huyền (01/01/2021, primary):
  <https://giayinthanhhuyen.com/upload/hinhanh/bang-gia-giay-in-kho-lon-thanh-huyen-01012021-8213.pdf>
- Cách tính báo giá offset — InMedia: <https://inmedia.vn/cach-tinh-bao-gia-in-offset/>
- Khổ giấy & định lượng — inhiflex: <https://inhiflex.vn/cac-loai-kho-giay-dinh-luong-giay-in-offset-pho-bien-theo-muc-dich-su-dung.html>
- In offset & quy trình — azoka: <https://azoka.vn/in-offset-la-gi-dac-diem-va-quy-trinh-cua-cong-nghe-in-offset.html>
- Khổ giấy — intietkiem: <https://intietkiem.com/kho-giay-in-offset/> · Quy đổi gsm — vprintpack:
  <https://vprintpack.com.vn/bang-so-sanh-quy-doi-dinh-luong-gsm-va-do-day-giay/>
- Tính giá offset (giấy) — giainoffset: <https://giainoffset.com/huong-dan-tinh-gia-offset-p3-giay-in-offset/>

**ERP / Print MIS (mô hình tham khảo):**
- Print MIS vs ERP — Sabre: <https://www.sabrelimited.com/blogs/print-mis-vs-erp-systems/>
- Sheet offset calculation — Dataline MultiPress:
  <https://www.dataline.eu/en/multipress/calculation/production-technology-calculation/sheet-offset-print-calculation>
- PrintVis guide: <https://erpsoftwareblog.com/2026/01/printvis-guide/>

---

---

# PHẦN VII — KẾT QUẢ PHẢN BIỆN ĐA CHUYÊN GIA & QUYẾT ĐỊNH THIẾT KẾ ⭐

> **Nguồn gốc chương này:** Tài liệu (PHẦN I–VI) được đưa qua **2 chuyên gia phản biện độc lập** rồi
> **tranh luận chéo 2 vòng**: (A) **Chuyên gia vận hành nhà máy in offset VN** (15+ năm điều hành
> xưởng) và (B) **Kiến trúc sư ERP/MIS ngành in** (người sẽ build). Chương này ghi lại **đồng thuận**
> giữa hai bên — đây là phần biến tài liệu từ "hiểu ngành" thành "đủ để thiết kế DB & API".
>
> **Kết luận lớn nhất:** PHẦN I–VI **đúng và chất lượng cao về kỹ thuật + khung module**, nhưng
> **"tuyến tính hóa" đúng ở những chỗ làm nên LỜI/LỖ thật của xưởng in**. 6 vùng dưới đây cần mô
> hình lại ở **mức cấu trúc** (không phải vá field), và một số phải đúng **ngay từ schema MVP-1**
> nếu không sẽ phải đập đi xây lại lõi costing/inventory/AR.

## 28. Bối cảnh & 6 vùng đồng thuận

| # | Vùng | Vấn đề của tài liệu gốc | Mức |
|---|---|---|---|
| 1 | **Ghép bài (gang-up)** | Giả định 1 job = 1 SP = 1 bộ kẽm; thực tế nhiều khách ghép 1 tờ in/1 kẽm/1 lượt canh → **nguyên tắc "mọi chứng từ link 1 job" VỠ** | 🔴 Lõi, P0 |
| 2 | **Quy trách nhiệm sự cố** | "In bù" coi là bước trung tính; thực tế *"ai chịu khi in lại"* = phần lớn mâu thuẫn tiền bạc | 🔴 Lõi, P0 (cột) |
| 3 | **Bù hao cộng dồn ngược** | Cộng % phẳng 1 lần là sai cho job nhiều công đoạn | 🔴 Công thức, P0 |
| 4 | **Lương khoán thực tế** | "Nguồn khoán = số đạt KCS" **sai** cho công đoạn in/giữa chuyền; thiếu đơn vị riêng & chia tổ | 🟠 P4, nhưng grain P0 |
| 5 | **Lệch pha Giao–Hóa đơn–Thu + công nợ** | Coi là 1 mạch; thực tế 3 sự kiện lệch pha, hạn mức không chặn cứng | 🟠 Lõi AR, P3 (grain P0) |
| 6 | **Giấy lẻ / giấy khách** | Coi giấy như chất lỏng đồng nhất; thực tế đầy giấy lẻ/đầu tấm | 🟡 P0 (field) + P5 (tối ưu) |

## 29. Mô hình 2 lớp: Job (thương mại) vs PrintForm (vật lý) — ghép bài

**Vấn đề:** ghép bài (gang-up) phổ biến tới **40–70% job** ở xưởng làm hàng nhỏ (name card, tem
nhãn, tờ rơi, hộp nhỏ). Khi 8 khách ghép lên 1 tờ in / 1 bộ kẽm / 1 lượt canh máy thì **1 tờ in vật
lý gánh N job** → mô hình "1 chứng từ – 1 job" không mô tả nổi.

**Quyết định:** tách **2 lớp** — *thương mại* (cái khách mua) và *vật lý* (tờ in thật):

```
Order 1─n Job 1─n JobItem ──┐  (THƯƠNG MẠI)
                            │ n
                      GangPlacement   (bảng nối: con nào của job nào, ở đâu trên form)
                            │ n
PrintForm 1─n FormPlate ────┘  (VẬT LÝ: tờ in, kẽm, lượt canh, bù hao set-up)
PrintForm 1─1 StockIssue        (giấy của FORM, không của job)
PrintForm 1─n JobOperation      (in/gia công của FORM)
```

```
PrintForm{ id, sheet_paper_master_id, pieces_per_sheet_total, planned_sheets,
           actual_sheets, makeready_sheets, plates_count, status,
           allocation_method ∈ {by_pieces, by_area, equal} }
GangPlacement{ print_form_id, job_item_id, pieces_on_form,
               share = pieces_on_form / pieces_per_sheet_total,
               status ∈ {active, cancelled_after_cost}, frozen_allocated_cost }
```

- **StockIssue / FormPlate / JobOperation link `print_form_id`, KHÔNG link `job_id`.** Job nhận chi
  phí **gián tiếp**: `allocated_cost(job, pool) = pool.amount × placement.share`, với pool ∈ {giấy,
  kẽm, công in, bù hao set-up}. Mặc định `share` theo **tỷ trọng số con**; cho cấu hình `by_area/equal`.
- **Một khách hủy giữa form:** chi phí form **đã phát sinh là cố định** → nếu hủy *sau khi in*, phần
  của khách hủy **chốt snapshot** (`frozen_allocated_cost`, thành khoản đền/ lỗ-có-fault), **KHÔNG
  tái phân bổ** cho các job còn lại (họ không gây ra). Hủy *trước khi ra kẽm* → gỡ placement, tính lại share.

> **⚠️ Sửa nguyên tắc kiến trúc #1 ở [§23](#23-thực-thể-dữ-liệu-cốt-lõi):** *"mọi chứng từ link 1
> job"* → **"mọi chứng từ sản xuất link 1 job HOẶC 1 PrintForm; chi phí form phân bổ về job theo
> `placement.share`."**
>
> **P0:** chèn abstraction `PrintForm` + `GangPlacement` ngay MVP-1 **kể cả khi case đầu chỉ 1 job/1
> form** — vì chèn sau khi đã có dữ liệu = đập lại toàn bộ costing + stock + operation.

## 30. Giá thành 3 lớp & quy trách nhiệm sự cố (fault_party)

**Vấn đề:** gộp mọi "hao hụt thực" vào giá thành biến **lỗ-do-thợ thành lỗ ẩn toàn job**, và làm
**sai lương khoán**. *"Ai chịu khi in lại"* là input trực tiếp của payroll, không phải tính năng phụ.

**Quyết định:** giá thành tách **3 lớp** + thực thể sự cố:

```
JobCostLine{ job_item_id, cost_pool,
             estimated_amount,        # từ định mức báo giá
             actual_within_norm,      # thực ≤ định mức → vào GIÁ VỐN (khách chịu)
             actual_variance,         # phần VƯỢT định mức
             variance_incident_id }   # → nguyên nhân
ProductionIncident{ id, print_form_id | job_operation_id, incident_type,
                    spoiled_qty, spoiled_cost,
                    fault_party ∈ {operator, prepress, customer, supplier_paper,
                                   supplier_finishing, machine, force_majeure},
                    disposition ∈ {absorb_cogs, charge_customer, deduct_payroll, claim_supplier} }
```

**Routing variance theo fault_party:**

| fault_party | disposition | Hệ quả |
|---|---|---|
| operator (thợ) | `deduct_payroll` | Phần in bù **KHÔNG tính khoán** (có thể trừ giấy/công); **KHÔNG vào giá khách** |
| prepress (chế bản) | `absorb_cogs` nội bộ | Lỗi nhà in; tách phòng chịu để báo cáo |
| customer | `charge_customer` | Đổi file/ý muộn → **tính thêm tiền khách** |
| supplier_paper/finishing | `claim_supplier` | **Đòi bồi thường NCC** (cấn trừ công nợ phải trả) |

→ Quyết toán [§8⑭](#8-quy-trình-từ-yêu-cầu-khách--giao-hàng) cho ra **P&L 3 dòng**: lãi gộp lý thuyết
/ variance ai chịu / lãi thực — thay vì 1 số lỗ không giải thích được.

> **P0 (cột):** `JobCostLine` phải tách `estimated / actual_within_norm / actual_variance` **ngay từ
> MVP-1** (tách cột rẻ; gộp rồi tách lại đắt). **Bảng `ProductionIncident` + fault_party phải xuất
> hiện NGAY khi có module sản xuất (MVP-2/3), KHÔNG đợi P4** — vì nếu không ghi nhận từ ngày 1 thì
> đến lúc tính lương khoán & quyết toán sẽ **không có dữ liệu lịch sử**.

## 31. Công thức then chốt

**(a) Số con trên khổ — NHẬP TAY + phần mềm gợi ý, KHÔNG tự khóa.**
Người bình bản cân nhắc thứ công thức không biết: kẹp nhíp (gripper 10–12mm), **canh thớ giấy** (để
gấp không nứt/đóng cuốn không vênh), thang màu (color bar) + dấu bắt chồng màu, bù xén giữa con, né
lằn gấp. Cùng 1 SP, thợ giỏi xếp 9 con, thợ kém 8 con = chênh lệch lời/lỗ. → **`pieces_per_sheet`
là field nhập tay**; phần mềm tính **gợi ý song song để cảnh báo** ("nhập 8, máy gợi ý tối đa 9?").
Công thức gợi ý:
```
usable_w = sheet_w − gripper − 2·edge_trim;  usable_h = sheet_h − 2·edge_trim
piece_w = finished_w + 2·bleed + gutter;     piece_h = finished_h + 2·bleed + gutter
gợi_ý = max( floor(usable_w/piece_w)·floor(usable_h/piece_h),     # thường
             floor(usable_w/piece_h)·floor(usable_h/piece_w) )    # xoay (loại nếu ràng buộc thớ)
```

**(b) Bù hao CỘNG DỒN NGƯỢC CHUỖI** (không cộng % phẳng):
```
# muốn giao đủ qty_final thành phẩm, tính LÙI từ cuối chuyền:
sheets_in = ceil( qty_final / (pieces_per_sheet · ∏ yield_rate(op_i)) )
total_print_sheets = base_sheets + makeready_sheets + running_waste
   makeready_sheets = makeready_per_color_side · colors · sides   # CỦA FORM (gang-up)
   running_waste    = base_sheets · running_waste_pct            # CỦA JOB/CÔNG ĐOẠN
```
→ Cần `JobOperation.yield_rate` (tỷ lệ đạt mỗi công đoạn, versioned). **Tách 2 cấp:** makeready in =
của **form**; running/finishing = của **job-item** — nếu trộn 1 công thức sẽ sai khi ghép bài (chỗ
§29 và §31 giao nhau).

**(c) Số lượt in (pass) khi vượt số đơn vị máy:**
```
số_pass = ceil( tổng_đơn_vị_in / số_đơn_vị_máy )
   # vd 4 CMYK + 2 pha + 1 UV = 7 đơn vị, máy 4 màu → 2 pass → ảnh hưởng số bản, công in, chồng màu, bù hao
```

## 32. In bù vs đơn bổ sung; đổi/hủy đơn theo mốc

**Phân biệt 2 loại "in thêm" (nếu gộp → giá thành bẩn + mất khả năng đo lỗi nội bộ):**

| | **In bù / Rework (nội bộ)** | **Đơn bổ sung (khách trả tiền)** |
|---|---|---|
| Bản chất | Lỗi nội bộ, không bán thêm | Khách xin in thêm |
| Mô hình | **Loop trong job** + `ProductionIncident` + fault | **Sub-job/đơn con** link job gốc |
| Giá bán | Không (khách trả như cũ) | **Có giá bán riêng** |
| Giá thành | Đè vào job gốc → **giảm lãi**, gắn fault_party | **Giá thành riêng** (giữ kẽm cũ nên rẻ hơn) |
| Lương khoán | **Không tính** (nếu lỗi tổ) | Tính bình thường |

**Đổi/hủy đơn — quy tắc theo MỐC THỜI ĐIỂM** (state machine phải có nhánh nghịch):

| Mốc | Giấy đã xuất | Kẽm | Cọc / chi phí |
|---|---|---|---|
| Trước khi ra kẽm | Nguyên ram → **nhập lại 100%** | Chưa có | Re-quote, gần như miễn phí |
| Sau khi ra kẽm | Bóc dở → phần in/canh = **hao thực**; còn lại **nhập lại dạng giấy lẻ** | **Bỏ, tính hết cho khách** (CTP không tái dùng) | Cọc trừ vào (kẽm + giấy đặc chủng + công đã chạy) |
| Đã in một phần | Giấy đặc chủng mua riêng → **khách ôm** | Sunk, gắn job | Hủy sinh **bút toán quyết toán hủy** = chi phí phát sinh − cọc |
| Tăng số lượng (kẽm còn dùng) | — | Giữ nguyên | Chỉ tính thêm giấy + công phần tăng |
| Đổi nội dung/khổ/số màu | — | **Phơi kẽm mới, tính cả 2 bộ** | — |

→ State machine bổ sung: `cancelled` (kèm `cancel_reason`, `cancelled_at_state` để biết hoàn/không
hoàn vật tư-cọc), `on_hold`, `reprint`(loop) vs `change_order`(re-quote giữ lịch sử). Định nghĩa
**bảng transition** `(from_state, to_state, required_role, guard, side_effects)`. Hai gate cứng:
`ordered` cần `quotation.approved AND deposit ≥ total·min_deposit_pct`; `in_production` cần
`proof.customer_approved`.

## 33. Lương khoán: đơn vị theo công đoạn + chia khoán tổ

**Đơn vị nghiệm thu RIÊNG theo từng công đoạn** (sai lầm hay gặp: nhét 1 đơn vị chung "số đạt KCS"):

| Công đoạn | Đơn vị khoán | Lưu ý |
|---|---|---|
| **In offset** | **Lượt in** (= tờ × màu) hoặc **số tờ chạy** | ⚠️ **KHÔNG** theo SP đạt KCS cuối chuyền — thợ in xong việc rồi, khâu sau hỏng không trừ họ |
| Cán màng | m² hoặc số tờ | |
| Bế / Ép kim | nghìn cái | |
| Gấp | nghìn tờ/cuốn | |
| Đóng cuốn / vào bìa | cuốn | |
| Xén | nhát / nghìn SP / ram | |
| Dán hộp | cái | |

→ `OutputRecord` phải có **đơn vị riêng theo công đoạn**; `PieceRate` theo **(công đoạn × đơn vị ×
loại SP)**, versioned. **Không** dùng 1 cột "số lượng đạt" chung.

**Cá nhân hay tổ:**
- **Công đoạn máy** (in, cán, bế máy lớn) → **KHOÁN TỔ rồi chia**: `tiền_1_người = tổng_khoán_tổ ×
  (hệ_số × công của người đó) / Σ(hệ_số × công cả tổ)`. Trưởng máy hệ số ~1.3–1.5, phụ 1.0 (con số
  chính xác **phải hỏi SVN**).
- **Công đoạn thủ công** (gấp tay, dán, bắt cuốn) → **khoán cá nhân** trực tiếp.

→ `OutputRecord` ở **mức tổ HOẶC cá nhân**; mức tổ cần `CrewAllocation{ employee_id, factor,
work_units }`. **Payslip gộp nhiều cơ chế trong cùng kỳ:** `Σ khoán + Σ công_nhật×đơn_giá_ngày + OT
+ phụ cấp (ca đêm/độc hại) − BHXH − TNCN`; mỗi ngày công gắn **chế độ lương của ngày đó**.

> **⚠️ `fault_party` là INPUT của payroll:** in bù do lỗi tổ → sản lượng đó **không tính khoán**.
> Không có fault_party ⇒ tính sai lương ⇒ **công nhân phản ứng ngay kỳ lương đầu ⇒ xưởng quay lại
> Excel.** Đây là lý do §30 không thể hoãn.

## 34. Cardinality bắt buộc & quy ước kỹ thuật

**Cardinality KHÔNG được khóa sai (chi phí đặt đúng grain ngay ≈ 0; refactor sau = cả module):**
- `Order 1─n Job` (1 đơn khách "1.000 catalogue + 500 poster + 2.000 name card" = 3 job); thực tế
  **n-n** giữa Order-line ↔ Job/PrintForm (ghép bài). **Không 1-1.**
- `Delivery / Invoice / Payment` = **3 bảng riêng, quan hệ n-n** (`DeliveryLine` ↔ `InvoiceLine` ↔
  `PaymentAllocation`). **Lãi/lỗ khóa ở `DeliveryLine.job_item_id`, KHÔNG ở Invoice** → 1 hóa đơn
  VAT gộp nhiều phiếu giao/nhiều job vẫn truy ngược được lãi/lỗ từng job; khách không lấy VAT vẫn
  tính được. `InvoiceLine.vat_pct` cho mỗi dòng có/không VAT.
- `StockLot{ lot_type ∈ {full_ream, partial, offcut}, actual_sheets, ownership ∈ {company, customer},
  owner_customer_id }` — đếm **tờ thực**, không suy từ kg; giấy khách (ứng giấy) cost=0 vào JobCost
  nhưng vẫn trừ tồn.
- `OutputRecord` ở **mức tổ, cho n-NV** ngay từ đầu (đừng 1-record-1-NV).

**Quy ước kỹ thuật (kiến trúc sư chốt):**
- **Snapshot giá + định mức lúc chốt đơn (copy-on-write)** — chứng từ lưu `unit_price_snapshot` /
  `norm_snapshot`, **KHÔNG chỉ FK bảng giá sống** (giá giấy nhảy hàng tuần → kéo FK = lỗ). **P0 bắt buộc.**
- **Versioning:** mọi bảng giá/định mức dùng `(effective_from, effective_to NULL=current)`.
- **Tiền:** lưu `DECIMAL(18,2)` hoặc integer VND; **chọn & ghi rõ** làm tròn ở dòng rồi sum (hay
  ngược lại); `currency` + `exchange_rate` snapshot cho mua ngoại; `vat_pct` là field (8/10% đổi
  theo chính sách).
- **Thời gian:** lưu UTC `timestamptz`, hiển thị Asia/Ho_Chi_Minh; phân biệt `date` (kỳ lương/kế
  toán) vs `timestamp` (sự kiện).
- **Công nợ:** **không chặn cứng** vượt hạn mức → `CreditOverride{ over_amount, reason, approver,
  audit }` + action RBAC `credit.override`; **netting AR↔AP** khi khách cũng là NCC.
- **Tồn kho:** `StockBalance{ on_hand, reserved, available }` + `StockReservation` (tạo ở lệnh SX,
  consume khi xuất); policy `allow_negative_stock=false`; giá vốn **bình quân gia quyền** cho MVP
  (thiết kế `StockLot` để sau nâng FIFO).
- **File:** `FileAsset{ entity_type, entity_id, kind ∈ {design, proof, po, pod, contract},
  storage_url, version, checksum }`; proof = FileAsset(kind=proof) + approval(customer).
- **Mực pha:** `InkRecipe` + `MixedInkLot{ pha/dùng/tồn_thừa, job gốc, hạn dùng }`.
- **Sản phẩm nhiều cấu phần:** `PrintProduct 1─n ProductComponent{ component_type(cover/body/insert),
  paper_master_id, colors_front/back, page_count, finished_w/h, bleed, grain_direction }` — bắt buộc
  cho sách/hộp.
- **Audit:** `AuditEntry{ actor, action, entity, before_json, after_json, at }` cho các action:
  approve_quote, approve_proof, issue_stock, reconcile_outsource, pay_salary, cancel_job, credit.override.
- **API:** chuẩn list `?page&size&sort&q&filters`; optimistic locking (`row_version`) cho
  Job/Quotation; danh sách chứng từ ([§9](#9-máy-trạng-thái-job--chứng-từ)) → mỗi cái 1 **PDF template**.

## 35. Lộ trình build (P0/P1/P2) & 2 câu hỏi sống còn

**Đồng thuận lộ trình** (đặt đúng grain ở P0 để không refactor xương sống):

- **P0 — bắt buộc trong schema MVP-1** (viết code thật 3 thứ đầu; còn lại chỉ cần đặt cardinality đúng):
  1. `PrintForm` + `GangPlacement` giữa Job và kẽm/giấy/công đoạn; chi phí form → job qua `share`. *(§29)*
  2. `JobCostLine` tách 3 cột `estimated / within_norm / variance`. *(§30)*
  3. Công thức bù hao ngược chuỗi `ceil(qty / ∏ yield_rate)`, tách makeready (form) vs running (job). *(§31)*
  4. Snapshot giá copy-on-write; `Order 1─n Job`; `Delivery/Invoice/Payment` 3 bảng n-n; `StockLot.lot_type
     + actual_sheets + ownership`; `OutputRecord` mức tổ n-NV. *(§34)*
- **P1 — MVP-2/3 (logic):** `ProductionIncident` + disposition routing; `StockReservation` + âm kho;
  `CreditOverride` + netting; giao–hóa đơn–thu lệch pha đầy đủ.
- **P2 — Phase 4–5:** `CrewAllocation` chia khoán tổ + payslip gộp; tối ưu pha khổ giấy lẻ; gang-up
  tự động (imposition) — MVP chỉ cần **nhập tay** placement.

**⚠️ 2 CÂU HỎI SỐNG CÒN — phải khảo sát Sao Việt Nhật TRƯỚC khi chốt schema MVP-1:**

1. **Tỷ trọng ghép bài (gang-up) của SVN là bao nhiêu %?** → quyết định `Order–Job` mở n-n ngay hay
   tạm 1-1. Xưởng hàng nhỏ (name card/tem/tờ rơi): 40–70% → **phải mở sớm**. Xưởng sách/bao bì lớn 1
   SP: ít → hoãn được. **Sai giả định này = đập lại costing engine ở P5.**
2. **Hệ số chia khoán tổ** (trưởng máy vs phụ máy) và **đơn vị khoán từng công đoạn** thực tế của
   SVN → quyết `PieceRate` + `CrewAllocation`. Không nguồn nào có; chỉ SVN trả lời được.

> *(Hai câu này bổ sung cho 9 vùng ở [§26](#26-cần-xác-nhận-với-nhà-máy-thực-tế).)*

**Khuyến nghị tiếp theo:** tạo tài liệu **`DATA_CONTRACTS.md`** (schema-level: trường + kiểu + khóa +
công thức pseudo-code) dựng trên PHẦN VII này, **trước khi** khởi động code MVP-1.

---

---

# PHẦN VIII — CƠ CẤU PHÒNG BAN & BẢN ĐỒ MODULE UI/RBAC ⭐

> **Nguồn gốc:** 3 vai phản biện độc lập × 2 vòng tranh luận — (1) **Chủ xưởng/GĐ điều hành** (đẩy
> tinh gọn + tổ chức thật), (2) **Trưởng Điều độ SX/PPC** (đủ mắt xích sản xuất), (3) **Kiến trúc sư
> ERP/UX** (IA sạch + gate RBAC). Chương này là **đồng thuận cuối** về *có những phòng ban nào* và
> *navbar có những module gì, để làm gì*.
>
> **Nguyên tắc trục:** **"Gọn ở lớp NHÌN, tách ở lớp GATE"** — navbar hiển thị ít mục (gộp bằng
> tab/drill-down), nhưng RBAC vẫn tách nhiều `module_key` để mỗi phòng gate độc lập. 1 mục navbar =
> 1 `module_key` (khớp cơ chế Sidebar tự lọc theo quyền đã có ở feat-010).

## 36. Cơ cấu phòng ban & kiêm nhiệm (RBAC N-N)

**Thực tế xưởng vừa VN (< ~60 người):** ~11 phòng "sách vở" nhưng chỉ **~5 cụm người thật**, phần
còn lại **kiêm nhiệm**. Vẫn định nghĩa đủ phòng ở RBAC (để phân quyền sạch), rồi cho **1 người giữ
nhiều vai xuyên phòng**.

| Phòng ban (RBAC) | Chức năng | Thực tế xưởng vừa |
|---|---|---|
| **Ban Giám đốc** | Duyệt giá/đơn lớn, quyết mua, quyết toán | Chủ **kiêm Điều độ + duyệt** |
| **Kinh doanh / CSKH** | Nhận đơn, báo giá, chăm khách, đòi nợ (AR) | Sale kiêm đòi công nợ của khách mình |
| **Chế bản / Kỹ thuật** (Pre-press) | File, bình bản, CTP, **pha mực**, proof | Riêng (2–4 người); pha mực do thợ lâu năm kiêm |
| **Điều độ sản xuất** (PPC) | Kế hoạch, lịch máy, ghép bài, mở lệnh SX | Thường **chủ/quản đốc kiêm** |
| **Xưởng in** (Tổ in) | Canh máy, in, OK-sheet, ghi sản lượng | Riêng (tổ trưởng máy) |
| **Xưởng thành phẩm** | Cán/bế/ép/gấp/đóng cuốn/xén | Chung 1 quản đốc với Tổ in |
| **KCS / QC** | Kiểm chất lượng + đếm số đạt | Thường tổ trưởng/quản đốc **kiêm** |
| **Kho** (+ Giao nhận) | Nhập–xuất–tồn, giao hàng | Thủ kho **kiêm mua + giao** |
| **Mua hàng / Vật tư** | Mua giấy/mực theo job, NCC | Kiêm với Kho hoặc do chủ/kế toán quyết |
| **Kế toán – Tài chính** | Thu/chi, hóa đơn VAT, công nợ, giá thành | 1 KT **kiêm AR+AP+quỹ+giá thành+nửa HCNS** |
| **HCNS** | Hồ sơ, chấm công, lương, BHXH | **Kiêm với Kế toán** |

> **⚠️ Quyết định RBAC (C6 — cả 3 vai đồng thuận, Chủ xưởng giữ cứng):** hệ hiện tại **1 user – 1
> vai – 1 phòng** KHÔNG chạy được (5 người thật đội ~12 mũ → phải tạo 12 user ảo → audit vô nghĩa).
> **Phải chuyển `user ↔ role` sang many-to-many:** 1 user gán nhiều cặp (vai trò, phòng).
> - Schema: **giữ nguyên** `User.role_id/department_id` làm **vai chính**; thêm bảng nối
>   `user_roles(user_id, role_id, is_primary)`. Migration: mỗi user hiện tại → 1 hàng `is_primary=true`.
> - `deps.py`: hợp quyền = **union** các `RolePermission` của mọi vai user giữ; mỗi `module_key` lấy
>   **OR cờ CRUD + max scope** (`own < department < all`). Sidebar không đổi (`readable` = union). Token
>   không đổi.
> - **Segregation of Duties (SoD):** cho kiêm nhiệm rộng NHƯNG khóa vài cặp nguy hiểm — *người xuất
>   kho ≠ người đối soát gia công*; *người tạo phiếu chi ≠ người duyệt chi trên ngưỡng*; *người mở
>   lệnh ≠ người ký duyệt mẫu thay khách*.
> - **Lộ trình:** P0 tạm seed vài **role kiêm nhiệm cứng** cho đúng 5 người để chạy ngay; **mở
>   `user_roles` M2M ở P1** trước khi thêm phòng thứ 6 (refactor càng muộn càng đắt — §34).

## 37. Bản đồ navbar chốt

Nhãn: **[MD]** master-data · **(tab)** = tab bên trong, không phải mục riêng · `module_key` in `code`
· **[P0/P1/P2]** lộ trình build. **Trần ≤ 6 mục/nhóm.**

```
TỔNG QUAN                                                        [P0]
└─ Dashboard                                    dashboard

KINH DOANH                                                       [P0]
├─ Khách hàng (CRM)                             khach_hang
├─ Báo giá   (tab: Tính giá thành)              bao_gia   + bao_gia.approve
└─ Đơn hàng & Hợp đồng                          don_hang  + don_hang.cancel

SẢN XUẤT                                                         [P1]
├─ Điều độ & Lịch máy                           dieu_do
│     ├ (tab) Kế hoạch / Tải          ├ (tab) Lịch máy: xếp theo FORM×máy×ca   ├ (tab) MRP soát vật tư
├─ Lệnh sản xuất / Job  (tab: Tờ in/Ghép bài)   san_xuat_job
├─ Chế bản & Duyệt mẫu  (tab: Bình bản · Pha mực) che_ban + che_ban.approve_proof
├─ Vận hành in                                  van_hanh_in
├─ Gia công (nội bộ · thuê ngoài · đặt in)      gia_cong  + gia_cong.reconcile
├─ KCS                                          kcs
├─ Sự cố & In bù (fault_party)                  su_co  + su_co.log + su_co.disposition
└─ Máy móc  [MD] (tab: Bảo trì [P2])            may_moc

KHO & THU MUA                                                    [P1]
├─ Tồn kho  (tab: Nhập · Xuất · Kiểm kê · BTP · Hàng đi/về GC)  kho + kho.issue
└─ Mua hàng & NCC                               thu_mua

GIAO HÀNG                                                        [P1]
└─ Phiếu giao hàng (POD, nhiều đợt)             giao_hang

TÀI CHÍNH – KẾ TOÁN                                              [P1→P2]
├─ Công nợ (AR/AP)                              cong_no + cong_no.credit_override
├─ Giá thành & Quyết toán                       gia_thanh + gia_thanh.close_job   [P1]
└─ Thu/Chi & Sổ quỹ  (tab: Hóa đơn VAT)         ke_toan                            [P2]

NHÂN SỰ & LƯƠNG                                                  [P1→P2]
├─ Nhân viên & Chấm công                        nhan_su
└─ Lương (khoán)                                luong + luong.pay                  [P2]

DANH MỤC & CẤU HÌNH  ★ toàn bộ [MD]                              [P0→P2]
├─ Sản phẩm in                                  san_pham            [P0]
├─ Giấy & Vật tư (+ bảng giá, versioned)        dm_giay_vat_tu      [P0/P1]
├─ Định mức & Bù hao (WasteRule, yield_rate)    dm_dinh_muc         [P1]
└─ Đơn giá khoán (PieceRate, CrewFactor)        dm_don_gia_khoan    [P2]

BÁO CÁO                                         bao_cao             [P2]

QUẢN LÝ HỆ THỐNG  (ĐÃ CÓ)                                        [P0]
└─ Người dùng · Phòng ban · Vai trò · Nhật ký
```

## 38. Danh sách module_key RBAC & ánh xạ phòng ban

**Action nghiệp vụ ngoài CRUD** (cổng chặn) hiện thực bằng mẹo *action = `module_key` phụ, bật bằng
`can_read`* → **không phải migrate `role_permissions`**.

| `module_key` | Dùng để làm gì | Build |
|---|---|---|
| `dashboard` | Tổng quan theo vai trò | P0 (đã có) |
| `khach_hang` · `bao_gia` (+`.approve`) · `don_hang` (+`.cancel`) | Kinh doanh: CRM, báo giá + duyệt giá, đơn/hợp đồng | P0 |
| `san_xuat_job` | Job/Lệnh SX + PrintForm/Ghép bài (§29) | P0/P1 |
| `che_ban` (+`.approve_proof`) | Chế bản, bình bản, pha mực, **ký duyệt mẫu** (gate ⑤) | P1 |
| `dieu_do` | Kế hoạch + lịch máy (theo Form) + MRP soát vật tư | P1 |
| `van_hanh_in` | Tổ in: OK-sheet, ghi tờ/giờ máy, sản lượng khoán | P1 |
| `gia_cong` (+`.reconcile`) | Gia công nội bộ/thuê ngoài/đặt in + đối soát | P1 |
| `kcs` | Kiểm chất lượng + đếm số đạt | P1 |
| `su_co` · `su_co.log` · `su_co.disposition` | **Sự cố/in bù**: ghi từ nhiều màn, route fault_party→lương/khách/NCC (§30) | P1 |
| `may_moc` | Danh mục máy (specs) + bảo trì; downtime khóa lịch | P2 |
| `kho` (+`.issue`) | Nhập/xuất/tồn/kiểm kê, StockLot, **xuất vật tư** (gate ⑧) | P0/P1 |
| `thu_mua` | PR→PO→GR→hóa đơn NCC + NCC | P1 |
| `giao_hang` | Phiếu giao hàng, POD, nhiều đợt | P1 |
| `cong_no` (+`.credit_override`) | AR/AP, tuổi nợ, **vượt hạn mức có duyệt** (§34) | P1 |
| `gia_thanh` (+`.close_job`) | Giá thành 3 lớp + quyết toán (§30) | P1 |
| `ke_toan` | Thu/chi, quỹ, hóa đơn VAT | P2 |
| `nhan_su` | Hồ sơ + chấm công (ca/kíp) | P1 |
| `luong` (+`.pay`) | Lương khoán, PieceRate, Payslip, **chi lương** | P2 |
| `san_pham` · `dm_giay_vat_tu` · `dm_dinh_muc` · `dm_don_gia_khoan` | Master-data (versioned) | P0→P2 |
| `bao_cao` | Báo cáo/dashboard nâng cao | P2 |
| `nguoi_dung` · `phong_ban` · `vai_tro` · `activity_log` | Quản trị hệ thống | Đã có |

**Ánh xạ phòng → quyền (R=đọc, W=ghi, ✓=action):** Kinh doanh→W`khach_hang/bao_gia/don_hang`,
✓`bao_gia.approve`(trưởng), R`gia_thanh`. Chế bản→W`che_ban`, ✓`approve_proof`, R`san_xuat_job`.
Điều độ→W`dieu_do/san_xuat_job`, R`bao_gia/kho/may_moc`. Tổ in→W`van_hanh_in/gia_cong`,
✓`su_co.log`, R`dieu_do`. KCS→W`kcs`, ✓`su_co.log/su_co.disposition`. Kho→W`kho/giao_hang`,
✓`kho.issue`. Mua hàng→W`thu_mua/dm_giay_vat_tu`(giá NCC), W`cong_no`(AP). Kế
toán→W`cong_no/ke_toan/gia_thanh`, ✓`credit_override/close_job`. HCNS→W`nhan_su/luong/dm_don_gia_khoan`,
✓`luong.pay`(trưởng). **Nguyên tắc: mỗi phòng GHI tập module rời nhau; chồng lấn chỉ ở READ.**

## 39. 6 quyết định đồng thuận (C1–C6)

| # | Xung đột | Chốt (đồng thuận 3 vai) |
|---|---|---|
| **C1** | Chế bản/Bình bản/Duyệt mẫu: mục riêng hay tab? | Navbar 2 mục (*Job* + *Chế bản*); **3 gate**: `san_xuat_job`, `che_ban`, `che_ban.approve_proof`. Bình bản & pha mực = tab trong Chế bản; PrintForm/Ghép bài = tab trong Job. *"Gọn ở nhìn, tách ở gate."* |
| **C2** | Kế hoạch SX vs Lịch máy | **1 `module_key` `dieu_do` + 2 tab** (Kế hoạch/tải · Lịch máy/dispatch). Lịch xếp theo **FORM×máy×ca** (ghép bài), **không solver** — nhập tay + cảnh báo trễ. |
| **C3** | KCS vs Sự cố/fault | **TÁCH**: `su_co` là thực thể/module riêng; `su_co.log` **ghi được từ nhiều màn** (KCS/Vận hành in/Gia công); `su_co.disposition` (route fault) chỉ KCS/Kế toán. `fault_party` cuối do **quản đốc duyệt**. |
| **C4** | MRP + Pha mực có lên navbar? | **Không** — MRP = tab trong `dieu_do` (soát vật tư + `StockReservation`, **gate mềm**: thiếu → cảnh báo + tạo PR); Pha mực (`InkRecipe/MixedInkLot`) = tab trong `che_ban`. |
| **C5** | Máy móc & Bảo trì đặt đâu? | `may_moc` = master-data (**ghi bởi Kỹ thuật**, cả `bao_gia` số pass & `dieu_do` phụ thuộc), **hiển thị dưới nhóm Sản xuất**. Downtime → `su_co.log(machine)` + khóa slot ở tab Lịch máy. Bảo trì đầy đủ = **P2**. |
| **C6** | RBAC kiêm nhiệm | **`user ↔ role` many-to-many** (bảng `user_roles`); hợp quyền = union ở `deps.py`; **giữ SoD** cho cặp nhạy cảm. Tạm role kiêm nhiệm cứng ở P0, mở M2M ở P1. |

> **Chốt "đã đầy đủ chưa":** Sau vòng phản biện này, danh sách **phòng ban + module navbar** đã phủ
> đủ và được 3 góc (vận hành/sản xuất/kiến trúc) đồng thuận. Việc build cần theo lộ trình P0→P2 và
> **sửa RBAC sang N-N (C6)** — đây là thay đổi nền quan trọng nhất so với hệ hiện tại.

---

# PHẦN IX — BỘ KHUNG CUỐI (BẢN LÀM VIỆC — CÒN CHỈNH) ⭐⭐

> **Trạng thái:** BẢN LÀM VIỆC (checkpoint) — hợp nhất **spec chính thức của khách** (6 phân hệ,
> mạnh kế toán MISA/TT200-133-80) với chiều sâu domain in (PHẦN I–VIII), qua 2 vai phản biện × 2
> vòng + nhiều lượt tinh chỉnh module với chủ đầu tư. **Một số điểm còn để ngỏ — xem cuối §43.**
> Nguyên tắc: giữ 6 phân hệ khách làm xương sống + THÊM phân hệ Nhân sự & Lương + bơm 9 construct
> in vào lớp schema/gate; chiều sâu in chạy ngầm dưới ngôn ngữ phân hệ quen thuộc.

## 40. Ba quyết định lớn (D1–D3)

### D1 — Phạm vi kế toán: HYBRID (SVN dùng **MISA**) ✅
Một chiều **ERP → MISA**. ERP là nguồn nghiệp vụ; MISA là sổ pháp lý.

| ERP GIỮ (chi tiết theo job) | KẾT XUẤT sang MISA (bút toán **tổng hợp theo kỳ**) |
|---|---|
| Giá thành job 3 lớp, P&L từng job; công nợ AR/AP; bảng kê xuất kho; bảng lương khoán; thu/chi-quỹ | Kết chuyển 632/154/155; số dư 131/331; 621/627; 622/334 |
| **KHÔNG** làm: NKC, sổ cái pháp lý, BCTC TT200/133, tờ khai thuế TT80, TSCĐ-CCDC + khấu hao | → để **MISA** |

ERP đẩy **bút toán tổng hợp** (không đẩy từng giao dịch lẻ) + bảng kê đính kèm; dựng **connector
MISA** (import Excel/XML hoặc API AMIS — chọn theo bản MISA của SVN). **Ranh giới đỏ:** ERP không
phát hành BCTC/tờ khai thuế.

### D2 — Ghép bài/PrintForm: schema n-n từ P0, UI ẩn khỏi Sale ✅
- `Order–Job–PrintForm` **many-to-many ngay MVP-1**. Sale/CRM chỉ thấy Đơn hàng → Job; **không
  thấy** PrintForm/kẽm/share. Điều độ/Chế bản là nơi duy nhất thao tác ghép bài. Không ghép → hệ tự
  tạo ngầm form `share=1.0`. Khẩu quyết: **"Sale nói bằng ĐƠN HÀNG · xưởng nói bằng TỜ IN · kế toán
  nhận theo JOB."**

### D3 — fault_party: duyệt theo ngưỡng + snapshot bất biến + điều chỉnh ngược ✅
- Duyệt phân cấp: Thấp (<X)→Quản đốc; Trung (X–Y)→+Kế toán; Cao (>Y) hoặc tính tiền khách/đòi NCC→GĐ.
  `su_co.log` (ai cũng ghi) ≠ `su_co.disposition` (hạn chế vai+duyệt); chỉ `approved` mới nuôi giá
  thành+lương; SoD người ghi ≠ người duyệt. *(Ngưỡng X/Y do SVN tự cấu hình.)*
- **Điều chỉnh ngược:** snapshot đã chốt **bất biến** → thay đổi = bản ghi mới ở kỳ hiện tại
  (`PayrollAdjustment` claw-back kỳ sau · credit/debit note → MISA · `PostClosingAdjustment`); cờ
  `is_locked`, disposition cũ → `superseded` + audit.

## 41. Bản đồ module (12 nhóm)

```
📊 TỔNG QUAN          • Dashboard

⚙️ QUẢN LÝ HỆ THỐNG   • Người dùng · Phòng ban · Vai trò/Phân quyền · Nhật ký
                      (kèm: tham số hệ thống · cấu hình MISA · duyệt đa cấp · backup)
                      RBAC: user↔role N-N (kiêm nhiệm) + SoD + phạm vi dữ liệu (của tôi/phòng/tất cả
                      + "theo TỔ")

💼 KINH DOANH         • Tính giá      (bảng tính giá thành: số con/khổ → giấy+kẽm+công in+GC → giá vốn)
                      • Báo giá       (từ Tính giá + lãi + chiết khấu + bậc SL + snapshot + duyệt)
                      • Khách hàng    (CRM: MST/check trùng, hạn mức, công nợ)
                      • Sản phẩm      (danh mục SP in + cấu phần bìa/ruột)
                      • Đơn hàng bán  (nội bộ/theo YC, cọc-gate, Order 1─n Job, giao hàng, hoa hồng, KH KD)

🏭 SẢN XUẤT           • Tổ & Đầu việc        (khai Tổ → đầu việc[1 tổ] + ĐƠN GIÁ KHOÁN + THÀNH VIÊN + hệ số)
                      • Kế hoạch sản xuất    (nhu cầu SX từ đơn, KH tháng/quý, MRP, đối chiếu; DÙNG định
                                              mức từ Danh mục)
                      • Lệnh sản xuất / Job  (chọn đầu việc → TỰ GÁN TỔ; + PrintForm/ghép bài; tiến độ)
                      • Lịch máy / Điều độ   (xếp Tờ in × máy × ca)
                      • Chế bản & Duyệt mẫu  (bình bản, pha mực, CTP, GATE khách ký duyệt — GIỮ RIÊNG)
                      • Thực hiện SX theo tổ (sổ TỔ theo quyền; mỗi tổ ghi sản lượng/hao hụt; In có
                                              OK-sheet/kẽm; công đoạn thuê ngoài có nút phiếu GC ngoài)
                      • KCS                  (đếm đạt/không đạt)
                      • Sự cố & In bù        (fault_party → nuôi lương khoán)

📦 KHO                • Kho hàng      (1 module — người dùng TỰ TẠO kho + khai hàng hóa; giấy họ×gsm×khổ
                                       / lô(nguyên ram/lẻ/đầu tấm) / giấy-khách(cost=0) chạy ngầm trong dữ liệu)

🛒 CUNG ỨNG           • Mua hàng & NCC (đề nghị mua→đơn mua→nhận hàng→công nợ phải trả; mua theo job)

🚚 GIAO HÀNG          • Phiếu giao hàng (POD, nhiều đợt)

💰 TÀI CHÍNH–KẾ TOÁN  • Công nợ (AR/AP)   • Giá thành & Quyết toán (3 lớp job-order)
                      • Thu/Chi & Sổ quỹ  (+ kết xuất bút toán tổng hợp → MISA)

👥 NHÂN SỰ & LƯƠNG    • Hồ sơ nhân sự & Hợp đồng   • Chấm công & Ca kíp (2–3 ca, ca đêm, tăng ca)
                      • Bảng lương (hỗn hợp: KHOÁN sản lượng[đơn giá/hệ số từ "Tổ & Đầu việc"] + thời gian
                        + phụ cấp[ca đêm/độc hại] + nghỉ phép; số trích BHXH + khấu trừ TNCN → kết xuất MISA)
                      Khai báo trong 3 module: ca làm việc · loại phụ cấp + hệ số OT(150/200/300+đêm30%)
                        · bậc thợ · loại HĐ(2 loại+thử việc) · loại nghỉ(phép 12, NNĐH 14/16)
                      ⏳ P1 (mở rộng sau, CHƯA làm): Tuyển dụng · Đào tạo & thi nâng bậc · ATLĐ đầy đủ
                        (khám SK/huấn luyện ATVSLĐ/BHLĐ/TNLĐ/quan trắc) · chế độ NNĐH đầy đủ · KPI/Thưởng-phạt
                        [nghề in = NNĐH loại IV theo TT11/2020: chế bản/vận hành in/pha mực/xén-bế]

🛠️ THIẾT BỊ & BẢO TRÌ  • Máy móc & Bảo trì (specs máy + bảo trì; downtime khóa lịch; OEE)

🗂️ DANH MỤC & CẤU HÌNH  • Giấy & Vật tư + bảng giá   • Định mức & Bù hao   • Chiết khấu
                        • Phương tiện vận chuyển   • Tài xế   • Khoản mục chi phí
                        (khai báo lẻ/dùng chung gom về đây; Sản phẩm→Kinh doanh, Đơn giá khoán→"Tổ
                        & Đầu việc", các khai báo gắn chặt phân hệ nào giữ tại phân hệ đó)

📈 BÁO CÁO            • Báo cáo (bán hàng/SX/tài chính/kho/năng suất)
```

**3 khái niệm mới cần nhớ (khác bản của 3 vai ở PHẦN VIII):**
- **Tổ & Đầu việc** — mô hình định tuyến: Tổ (1) ─< Đầu việc (n), *1 đầu việc thuộc đúng 1 tổ*. Chọn
  đầu việc khi lên công đoạn LSX → tự gán tổ. Mỗi đầu việc mang **đơn vị + đơn giá khoán** → nuôi
  luôn định tuyến + tiến độ + lương khoán. **Thành viên tổ gán ngay tại đây** (không ở Phân quyền).
- **Thực hiện SX theo tổ** (gộp "Vận hành in" + "Gia công" cũ) — 1 màn; "sổ xuống" danh sách tổ
  **lọc theo quyền**: ai thuộc/được xem tổ nào chỉ thấy tổ đó. In & thuê-ngoài là nút đặc thù trong
  màn, không phải module riêng.
- **Chế bản & Duyệt mẫu giữ riêng** — vì có cổng ký duyệt mẫu của khách (chặn cả job, dính bên
  ngoài), khác bản chất "tổ ghi sản lượng".

## 42. Ánh xạ nghiệp vụ → định khoản (kế toán hybrid)

Bảng `AccountingMapping{ event_type, debit_acc, credit_acc, amount_source, dimension, vat_pct }` —
**do Kế toán trưởng SVN cấu hình một lần** (mặc định TT200, versioned):

| Nghiệp vụ (ERP) | Nợ / Có |
|---|---|
| Xuất kho NVL cho SX (theo form/job) | Nợ 621 / Có 152 |
| Nhân công trực tiếp (lương khoán) | Nợ 622 / Có 334 |
| Chi phí SX chung (khấu hao máy, điện) | Nợ 627 / Có 214, 331 |
| Nhập kho thành phẩm (kết chuyển giá thành job) | Nợ 155 / Có 154 |
| Giao hàng → giá vốn | Nợ 632 / Có 155 |
| Hóa đơn bán (AR) | Nợ 131 / Có 511, 3331 |
| Thu tiền/cọc | Nợ 111,112 / Có 131 |
| Hóa đơn NCC giấy/mực (AP) | Nợ 152,1331 / Có 331 |
| Gia công ngoài | Nợ 154/627 / Có 331 |
| In bù lỗi thợ (`deduct_payroll`) | KHÔNG vào 621/622 job — treo nội bộ (1388/811) |

## 43. Tham số cấu hình + P0 schema + điểm còn ngỏ

**Tham số SVN tự nhập trong app (versioned, KHÔNG hardcode):** tích hợp MISA (bản MISA, TT200/133,
kỳ đẩy, nơi phát hành hóa đơn) · ngưỡng duyệt X/Y · đơn giá + đơn vị khoán từng đầu việc (ở Tổ &
Đầu việc) · hệ số chia khoán tổ · % bù hao/yield_rate/định mức · giá giấy/vật tư.

**9 P0 schema bất biến (đúng từ MVP-1, sai = đập lõi):**
1. `PrintForm` + `GangPlacement` (chi phí form→job qua `share`; auto share=1.0 khi không ghép).
2. `JobCostLine` 3 cột `estimated/actual_within_norm/actual_variance` + `variance_incident_id`.
3. Bù hao ngược chuỗi `sheets_in = ceil(qty/(pieces_per_sheet·∏ yield_rate))`; tách makeready(form) vs running(job).
4. Số bản kẽm = màu×mặt (BIẾN); `pieces_per_sheet` nhập tay + gợi ý; số pass = ceil(đơn vị in/đơn vị máy).
5. Snapshot giá + định mức copy-on-write lúc chốt; versioning `(effective_from, effective_to)`.
6. Cardinality: `Order 1─n Job`; `Delivery/Invoice/Payment` n-n (lãi/lỗ ở `DeliveryLine.job_item_id`);
   `OutputRecord` mức tổ n-NV; `user↔role` N-N; `JobOperation.đầu_việc → tổ` (1 đầu việc → 1 tổ).
7. `StockLot {lot_type, actual_sheets, ownership, owner_customer_id}` (đếm tờ thực; giấy khách cost=0 vẫn trừ tồn).
8. `IncidentDisposition` versioned + status + hook `DispositionAdjustment` (reversing, không sửa snapshot).
9. Lớp kết xuất bút toán tổng hợp sang MISA (không nhúng NKC/BCTC vào ERP).

### ✅ Đã chốt thêm (2026-07-01)
- **Kinh doanh — Tính giá TÁCH riêng khỏi Báo giá:** *Tính giá* = giá thành/giá vốn nội bộ (kỹ
  thuật/estimator làm; có thể nhiều phương án giấy); *Báo giá* = phiếu gửi khách = giá thành + lãi
  + chiết khấu + bậc SL + snapshot + duyệt. Báo giá tham chiếu kết quả Tính giá.
- **Nơi khai báo:** danh mục lẻ/dùng chung (giấy & vật tư, **định mức & bù hao**, chiết khấu,
  phương tiện vận chuyển, tài xế, khoản mục chi phí) → **Danh mục & Cấu hình**; khai báo gắn chặt 1
  phân hệ giữ tại đó (Khách hàng/Sản phẩm→Kinh doanh · Tổ & Đầu việc→Sản xuất · Máy→Thiết bị ·
  Kho→Kho · Nhân viên→Nhân sự).

### ⏳ Điểm còn để ngỏ (bàn & chỉnh sau)
- **Sản xuất: giữ 8 module hay gọn 6** (gộp *Kế hoạch SX + Lịch máy* → "Điều độ & Kế hoạch"; gộp
  *KCS + Sự cố* → "KCS & Sự cố"). Hiện đang để **8**.
- Rà lại ranh giới **Máy móc (Thiết bị) ↔ Lịch máy (Sản xuất)** khi dựng chi tiết.

---

> **Cảnh báo chung:** Số liệu thương mại/vận hành VN (giá ram, % bù hao, tốc độ máy, lương khoán,
> định mức gia công) là **giá trị tham khảo có phiên bản**, không phải hằng số — phải xác nhận với
> Sao Việt Nhật. Số liệu kỹ thuật/tiêu chuẩn (ISO/G7/ICC) ổn định; vài chuẩn trong ngữ cảnh G7
> (ISO 12647-2:2004, FOGRA39) là bản lịch sử (đã có 2013 / FOGRA51-52).
>
> *Tài liệu domain hợp nhất cho ERP Sao Việt Nhật — PHẦN I–VI (deep-research + tập quán xí nghiệp
> in, 2026-06-30); PHẦN VII (2 vai×2 vòng) + VIII (3 vai×2 vòng: phòng ban & navbar/RBAC) + IX (hợp
> nhất spec khách × domain in — BẢN LÀM VIỆC, còn chỉnh) bổ sung 2026-07-01.*
