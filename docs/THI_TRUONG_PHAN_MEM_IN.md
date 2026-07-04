# Thị trường phần mềm ngành in ấn & Domain nghiệp vụ in

> **Mục đích:** Benchmark cho ERP nhà máy in offset đang tự xây (dự án SVN — stack FastAPI + React, tích hợp MISA).
> **Nguồn:** Nghiên cứu đa nguồn có kiểm chứng đối kháng (deep-research 2026-07-03) — 20 nguồn, 76 luận điểm, kiểm chứng 25 luận điểm quan trọng (**23 xác nhận / 2 bị bác**). Ký hiệu `[3-0]` = 3/3 phiếu xác nhận.
> **Cảnh báo nguồn:** Phần lớn claim về năng lực sản phẩm dựa trên trang vendor / thông cáo báo chí — là *năng lực được quảng bá*, chưa benchmark hiệu năng độc lập. Vùng giá là yếu nhất.

---

## MỤC LỤC
- [A. Domain nghiệp vụ in ấn (nền tảng)](#a-domain-nghiệp-vụ-in-ấn-nền-tảng)
- [B. Thị trường phần mềm in ấn](#b-thị-trường-phần-mềm-in-ấn)
- [C. Đối chiếu cho SVN (benchmark)](#c-đối-chiếu-cho-svn-benchmark)
- [D. Nguồn tham khảo](#d-nguồn-tham-khảo)

> 📄 **Tài liệu liên quan:** [DANH_MUC_TINH_GIA.md](./DANH_MUC_TINH_GIA.md) — các danh mục cấu hình cần khai để tính được giá (sơ đồ danh mục → biến công thức).

---

## A. DOMAIN NGHIỆP VỤ IN ẤN (nền tảng)

### A1. Kỹ thuật in offset
- **Nguyên lý:** bản kẽm (nhôm) → cao su offset → giấy; cơ chế đẩy dầu–nước. In CMYK, ảnh ≥300 dpi, RIP ≥2400 dpi. CTP (computer-to-plate) bỏ khâu phim.
- **Đơn vị vật lý quyết định giá:**
  - *Số bản kẽm = số màu × số mặt* (BIẾN — không cố định 4 CMYK).
  - *Lượt in (impression) = số màu × số tờ.*
- **Giấy Việt Nam:** KHÔNG dùng ISO A/B. Khổ thực tế tính **cm, cạnh ngắn trước** (phổ biến 65×86, 79×109; thêm 60×84, 65×97…). Bán theo **ram (~500 tờ) + kg**. 5 họ giấy: Ford, Couche, Ivory/Bristol, Duplex; định lượng gsm ~58–500.
- **QC:** ISO 12647-2, chuẩn G7 (cân bằng xám / NPDC).

### A2. Quy trình sản xuất (14 bước rút gọn)
```
Yêu cầu KH → Tính giá → Báo giá → Chốt đơn → Thiết kế/Chế bản
→ Duyệt mẫu (proof) → CTP ra kẽm → Ghép bài (imposition) → In
→ Gia công (cán/bế/cấn/đóng) → KCS → Giao hàng → Công nợ
```

### A3. Công thức tính giá thành offset (cost-plus)
```
Giá vốn = Giấy + Kẽm + Công in (canh máy + lượt in) + Mực + Gia công + Bù hao
Số tờ in = ceil(SL / số-con-trên-khổ / ∏ tỷ_lệ_đạt) + bù hao (makeready + running)
Doanh số = Giá vốn / (100% − Lãi suất)
Tiền lãi = Lãi suất × Doanh số
```
- Phí cố định (kẽm, canh máy, bù hao makeready) khiến **in càng nhiều → càng rẻ trên đơn vị** (phân bổ phí cố định).
- Lãi suất thường theo **bậc thang** theo ngưỡng giá vốn.

### A4. Thực thể dữ liệu cốt lõi
`Customer` · `PrintProduct` · **`PaperMaster`** (họ × gsm × khổ, giá per-ram & per-kg, **versioned — không hardcode**) · `BOM/định mức` · **`Plate/Impression`** · `WasteRule` · `Machine` + lịch máy · `Quotation engine` · **`JobTicket`** · **`PrintForm/GangPlacement`** (tách "tờ in vật lý" khỏi "đơn thương mại" để xử lý ghép bài) · `OutsourcedFinishing` · `PieceworkLabor` (lương khoán theo công đoạn).

---

## B. THỊ TRƯỜNG PHẦN MỀM IN ẤN

### B1. Hai tầng sản phẩm: Print MIS vs Print ERP `[xác nhận 3-0]`

| Tiêu chí | **Print MIS** | **Print ERP** |
|---|---|---|
| Trọng tâm | Quản lý *thông tin sản xuất*: tính giá, lập lịch, theo dõi job, tồn kho | MIS + *toàn doanh nghiệp*: tài chính, CRM, mua hàng/chuỗi cung ứng, kho, sản xuất |
| Tích hợp | Thường phải nối phần mềm kế toán ngoài | Tích hợp đầy đủ trên một nền |

> Ranh giới đang **mờ dần** — MIS hiện đại bổ sung tự động hóa nên tiệm cận ERP. *(wye.com, Sabre Limited, Print ePS)*

### B2. JDF / JMF — chuẩn tích hợp quan trọng nhất `[xác nhận 3-0, nguồn CIP4 primary]`
- **JDF** (Job Definition Format — CIP4, ra đời **2000**): job ticket dạng XML mô tả toàn bộ vòng đời job — từ ý định khách hàng → thông số prepress / press / finishing.
- **JMF / XJMF** (Job Messaging Format): thông điệp XML **thời gian thực** giữa MIS ↔ thiết bị xưởng (nộp job, tracking, tiêu hao vật tư, điều khiển queue/pipe).
- **Vai trò:** đây là **điểm tích hợp mấu chốt** giữa máy móc xưởng in và tầng MIS/ERP → cho phép *pre/post-calculation* (đối chiếu giá dự toán vs chi phí thực tế) một cách tự động.
- **Hệ quả cho SVN:** bất kỳ Print MIS/ERP nghiêm túc nào cũng thiết kế xoay quanh JDF/JMF. SVN cần quyết sớm: hỗ trợ JDF/JMF cho tích hợp máy CTP/in/bế, hay dựa vào job ticket thủ công (tùy nền thiết bị thực tế).

### B3. Sản phẩm quốc tế `[xác nhận 3-0]`

Phân khúc theo quy mô xưởng:

| Nhóm | Sản phẩm | Ghi chú |
|---|---|---|
| **Xưởng nhỏ / quick print** | Printavo, ShopVOX, Ordant, Keyline, Printer's Plan | Rẻ, cloud, dễ dùng |
| **Vừa – lớn (commercial)** | **Tharstern, PrintVis, Avanti Slingshot, eProductivity/EFI PACE, PrintIQ, HiFlow, Accura, PressWise** | MIS/ERP đầy đủ, giá custom-quote |
| **Workflow / tự động hóa thiết bị** | **Heidelberg Prinect**, HP PrintOS, Esko | Gắn máy in / CTP / bế |

**Đáng chú ý cho SVN:**

- **PrintVis** `[3-0]` — MIS/ERP **nhúng hoàn toàn trong Microsoft Dynamics 365 Business Central**: không phải MIS đứng riêng, thừa hưởng tài chính / CRM / báo cáo của BC (chung một database), khỏi cần phần mềm kế toán tách rời. Đây là **mô hình quốc tế gần nhất với mục tiêu SVN tích hợp MISA**. Chức năng lõi: estimating/quoting, job costing, production planning, shop-floor với electronic job ticket real-time, tồn kho, CRM, hóa đơn. Nhắm mọi quy mô nhà in (commercial, packaging, label, large format, apparel, quick print) — **không khuyến nghị cho startup** (phức tạp, chi phí cao; triển khai ~$36k–$100k+).

- **EFI / eProductivity PACE** `[3-0]` — Print MIS tiêu biểu. Module lõi: estimating/quoting, production scheduling, job tracking, inventory, kế toán tích hợp, CRM.

- Products được **phân khúc theo quy mô** (vd Printer's Plan = nhỏ–vừa; Midnight = vừa–lớn cho nhà in/mailer).

### B4. Sản phẩm Việt Nam `[xác nhận — confidence medium: chỉ có trang vendor, không có review độc lập / case study có tên khách hàng]`

- **NextPrint** (Trí Thành Software) — Print MIS/ERP nội địa rõ nét nhất, tổ chức thành **8 phân hệ**:
  1. Tính giá in
  2. Quản lý đơn hàng
  3. Kho vật tư
  4. Mua hàng
  5. Kế hoạch sản xuất
  6. Quản lý sản xuất
  7. Nhân sự / Lương
  8. Thu chi (tài chính)

  → Cấu trúc **gần trùng khớp bản đồ module SVN đang xây** — đối thủ nội địa sát nhất để đối chiếu.

- **MekongSoft / Phần mềm Việt** — phần mềm quản lý xưởng in offset / bao bì / quảng cáo, tùy biến, nhắm nhà in nhỏ–vừa.

- **giainoffset.com** `[xác nhận 3-0]` — công cụ tính giá offset (Excel) mã hóa đúng logic domain SVN cần:
  - **Cost-plus:** giấy + công in + nhân công/overhead + **bù hao in** + lãi bậc thang; xác nhận verbatim `Tiền lãi = Lãi suất × Doanh số` và `Doanh số = Giá vốn / (100% − Lãi suất)`.
  - **Bình bài tự động ("Bình Bài Tự Động")** tự chọn 1 trong **4 kiểu layout** theo thông số / số lượng / khổ máy:
    | Kiểu | Tên VN | Tên EN | Logic chọn |
    |---|---|---|---|
    | 1 | In 1 Mặt | Single-sided | 1 mặt |
    | 2 | In Tự trở | Work-and-turn | số con chẵn, chia 2 theo cạnh dài |
    | 3 | In Trở nhíp | Work-and-tumble | trở theo cạnh ngắn |
    | 4 | In A-B | Sheetwise / separate forms | khi tờ chung không là bội số kích thước sản phẩm |
  - → Là **template cụ thể cho engine bình bài + bù hao của SVN**.

### B5. Xu hướng `[xác nhận 3-0]`
- **Cloud + AI tự động hóa + hybrid offset/digital.**
- **Prinect Touch Free** (Heidelberg — AI, native cloud): tự tính *mọi* phương án bình bài/layout, tự lập trình tự sản xuất, và **tự quyết sản phẩm in bằng offset hay digital**. Tại Galledia Print AG, Prinect điều phối tự động ~50 đầu tạp chí.
- **HP PrintOS Production Hub** (ra mắt 5/2025): nền tập trung real-time để nhận đơn + điều khiển queue máy in từ xa trên **một giao diện** (thay vì từng thiết bị rời).

### B6. Giá & phân khúc — VÙNG YẾU NHẤT `[2 luận điểm BỊ BÁC]`
- ❌ **Bác (0-3):** "ngành đã chuyển sang tính tiền theo **số user** thay vì số máy in" → **không đúng**.
- ❌ **Bác (1-2):** bảng giá tier cụ thể (vd Printavo ~$139/mo, ShopVOX ~$149/mo) → **không kiểm chứng được**, coi như chưa xác nhận.
- ✅ **Chắc chắn:** hệ enterprise (Tharstern, PrintVis, Avanti, HiFlow) đều **báo giá custom**, không niêm yết công khai.

---

## C. ĐỐI CHIẾU CHO SVN (benchmark)

| Năng lực chuẩn thị trường | SVN đang có? | Ghi chú |
|---|---|---|
| Estimating / tính giá offset cost-plus | ✅ Có | `pricing_engine`, tách Tính giá ≠ Báo giá |
| Imposition / ghép bài | ⚠️ Một phần | Có `PrintForm`/`GangPlacement` + gợi ý số con/khổ; **nên bổ sung 4 mode như giainoffset** |
| Job ticket / shop-floor real-time | ✅ Có | `JobTicket` + màn "Thực hiện SX theo tổ" |
| Scheduling / lịch máy | ✅ Có | Điều độ + Lịch máy (xếp theo FORM, chưa solver) |
| MIS/ERP + kế toán | ✅ Hybrid | ERP + **đẩy bút toán tổng hợp sang MISA** — giống mô hình PrintVis↔BC nhưng loosely-coupled |
| **JDF / JMF (tích hợp máy CTP/in/bế)** | ❌ Chưa | **Khoảng trống lớn nhất** so với quốc tế |
| Web-to-print | ❌ Chưa | Có cổng khách ký duyệt proof |
| CRM | ⚠️ Một phần | Có Khách hàng, chưa CRM đầy đủ |

### Khuyến nghị rút ra
1. **JDF/JMF** là điểm tích hợp thiết bị mà mọi MIS/ERP quốc tế đều xoay quanh → SVN nên quyết sớm: triển khai JDF/JMF hay dựa job ticket thủ công (tùy nền thiết bị thực của SVN).
2. **Mô hình PrintVis (nhúng trong BC)** là bản tham chiếu cho câu hỏi kiến trúc: MISA sync lỏng có đủ không, hay cần single-database để job-costing chính xác hơn?
3. **giainoffset** là template domain sát nhất cho engine bình bài + bù hao → đối chiếu trực tiếp khi hoàn thiện đặc tả #7 (sản phẩm nhiều cấu phần) và logic imposition.

### Câu hỏi còn ngỏ (research không chốt được)
- Giá / TCO thực của hệ enterprise (PrintVis/BC, Tharstern, Avanti, PrintIQ) — license model, per-seat vs per-site, chi phí triển khai.
- Độ sâu hỗ trợ JDF/JMF trong công cụ thị trường VN.
- Mức độ triển khai thật, độ sâu tính năng, độ chính xác tính giá offset của NextPrint / MekongSoft / giainoffset — không tìm thấy review độc lập hay case study có tên khách hàng.

---

## D. NGUỒN THAM KHẢO

**Primary (chuẩn / vendor gốc):**
- CIP4 — JDF: https://www.cip4.org/print-automation/jdf
- CIP4 — Job tickets: https://www.cip4.org/Print-Automation-Overview/articles/jobtickets
- CIP4 — (X)JMF (PDF, seminar 03/2024)
- Heidelberg — Prinect / Prinect Touch Free: https://www.heidelberg.com
- HP Newsroom — PrintOS Production Hub (05/2025)
- PrintVis: https://printvis.com

**Secondary / blog (đối chiếu):**
- AppIntent — "15 Best ERP Systems for Print Shops in 2026": https://www.appintent.com/software/ERP/printing-industry/
- SoftwareConnect — PrintVis review: https://softwareconnect.com/reviews/printvis/
- Gelato — PrintIQ alternatives 2026
- wye.com — Print MIS vs Print ERP
- Print ePS — PACE Print MIS: https://printepssw.com/pace-print-mis-software
- Sabre Limited — What is PrintVis
- ERP Software Blog (01/2026)
- Print Reach — chi phí phần mềm quản lý in

**Việt Nam:**
- Trí Thành Software (NextPrint): https://www.trithanhsoft.com/san-pham/phan-mem-quan-ly-xuong-in-an/
- Phần mềm Việt: https://phanmemviet.com.vn/profession/in-an-quang-cao
- MekongSoft: https://mekongsoft.com.vn
- giainoffset — hướng dẫn tính giá: https://giainoffset.com/tinh-gia-in-offset-huong-dan-su-dung/

---
*Tài liệu tạo tự động từ deep-research 2026-07-03. Liên quan: `docs/DOMAIN_NHA_MAY_IN.md` (domain nghiệp vụ hợp nhất).*
