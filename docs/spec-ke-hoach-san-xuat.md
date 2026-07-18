# SPEC — KẾ HOẠCH & LỆNH SẢN XUẤT (Đơn chốt → Ghép bài → Xưởng)

> Chốt qua thảo luận **2026-07-18** với chủ xưởng. **Spec thiết kế — CHƯA code.**
> Thay bản cũ (mô hình *1 đơn–1 lệnh, ghép bài hoãn Pha 5*) — bản cũ sai giả định: SVN **ghép bài ~40%+**.
> Anh em: `DOMAIN_NHA_MAY_IN.md` (§8 luồng · §29 ghép bài 2 lớp · §31 công thức), `spec-cong-doan.md`
> (routing/tổ), `spec-tinh-gia.md` + PTG/`thanh_phan_engine` (nguồn kế thừa quy cách), `DB_SCHEMA.md`.
>
> **KIM CHỈ NAM:**
> - **MÁY CHỈ GHI NHẬN** — người kế hoạch quyết, máy ghi lại. KHÔNG tự lọc / validate / cảnh báo /
>   tính-hộ trừ khi được yêu cầu. Phán đoán nghiệp vụ để con người.
> - ĐỌC quy cách / routing / vật tư từ **PTG**, đừng chép lại.
> - Ghép ở cấp **TỜ IN**, không phải cấp lệnh. **Lệnh = 1 ấn phẩm = 1 routing.**
> - Số con **NHẬP TAY** (dàn bài là việc chế bản ngoài ERP; ERP chỉ ghi "cái bóng kế toán").
> - Dẫn xuất (kẽm / lượt / share) do **ENGINE** tính. **TÁI DÙNG** (`routing_engine`, `department_id`,
>   `piece_work`, Kho, Mua hàng), đừng đẻ bảng song song.

## 0. CORE — kim chỉ nam đọc-trước (chống bias khi build tiếp)
> Chốt qua nhiều vòng với chủ xưởng (2026-07-18). Đây là "cái VÌ SAO" — đọc trước §1..§13. Nếu build
> mà thấy mình sắp làm ngược điểm nào ở đây thì DỪNG, hỏi lại. Các bias tôi hay mắc ghi ở cuối mục.

**A. Nguyên tắc gốc**
1. **Xây TỪ TRÊN xuống** — chủ xưởng phải NHÌN được xưởng đang làm gì + phải ĐỦ ĐIỀU KIỆN mới sản
   xuất. Bắt đầu từ màn giám sát/tổ, KHÔNG từ màn nhập liệu của thợ.
2. **MÁY CHỈ GHI NHẬN, người quyết** — không tự phán, không MRP, không tự quy lỗi/trừ khoán. Chỉ có
   **cổng cứng vì toàn vẹn** (chưa phát→chặn ghi; chưa tới lượt→chặn), KHÔNG phải máy phán nghiệp vụ.
3. **UI/UX ưu tiên cao nhất** — không "chữ + form" thô; soi–thiết kế → build → styleseed → xem tận mắt.
4. **Gộp vào luồng đang có, KHÔNG đẻ màn/loại/luồng riêng.** Không rõ gộp đâu → HỎI.
5. **Ảnh chủ gửi = tham khảo look/feel, KHÔNG phải flow.** Flow theo spec.

**B. Kiến trúc & luồng**
- 3 tầng khóa cardinality: **Đơn chốt → Lệnh SX (1 ấn phẩm = 1 routing, trỏ `phieu_thanh_phan_id`)
  → Tờ in (ghép n–n)**. Ghép ~40%+ nên tờ in là thật.
- Luồng người: kế hoạch **setup chi tiết lệnh** (routing + ghép tờ + gán máy + duyệt mẫu) → **PHÁT
  HÀNH** → **chỉ tổ CÓ CÔNG ĐOẠN TRONG ROUTING nhận lệnh (realtime)**, không bắn tổ ngoài routing.
- Phòng ban là nền: tick **"là sản xuất"** 1 phòng → phòng đó **+ cả cây con** vào phân hệ Sản xuất,
  **hiện DẠNG CÂY**. "Effective" = tự tick HOẶC tổ tiên tick (đi ngược `parent_id`) — **1 nguồn sự
  thật, không cascade lưu**.

**C. Các điểm CHỐT CỨNG (đúng chỗ hay bias)**
6. **"Kế thừa từ tính giá" = GIÁ TRỊ MẶC ĐỊNH, KHÔNG read-only.** Màn Lệnh (CẤU HÌNH) routing + quy
   cách in **PHẢI cho SỬA/override** trước khi phát. Copy sang `routing_step` (bản riêng mỗi lệnh) →
   sửa không đụng bảng giá. *(Bias tôi mắc nặng nhất — "chốt xong lại quên".)*
7. **Màn Lệnh = 2 chế độ:** NHÁP = **CẤU HÌNH** (sửa routing/tờ in/máy/duyệt + nút PHÁT HÀNH, ẩn
   runtime rỗng) ↔ ĐANG CHẠY/XONG = **THỰC THI**.
8. **Tổ view:** cây tổ → lệnh của tổ → màn thực thi. Tổ thấy NGUYÊN lệnh + routing, nhưng **chỉ thẻ
   công đoạn CỦA TỔ MÌNH + đúng bước ĐẾN LƯỢT** mới thao tác; bước khác chỉ xem. "Đến lượt" = bước
   hiện hành thuộc tổ. Routing dạng **THẺ** (chờ/đang/xong + Bắt đầu/Hoàn thành qua quét QR).
   → **Read-only routing Ở MÀN TỔ là ĐÚNG** (cấu hình nằm ở màn Lệnh/nháp) — KHÔNG phải tái bias.
9. **Giao nhận 2 CHIỀU:** tổ giao ghi `so_giao`, tổ nhận xác nhận `so_nhan` — **LỆCH ĐƯỢC**; máy hiện
   chênh lệch, KHÔNG phán ai sai, lý do ghi tay. **Phiếu bàn giao IN ĐƯỢC** (2 ô ký + QR).
10. **Realtime ĐÍCH DANH:** tổ A xong công đoạn → đẩy THẲNG tới tổ B (tổ bước kế) "đến lượt" → tổ B
    "ting" → sang tổ A lấy hàng. Badge nhảy + toast tức thì, không bắt refresh.
11. **Thợ in ít học → màn TEXTLESS:** biến thể cùng luồng, quét QR → 1 việc đến lượt + nút to, icon/
    màu/số to, không đọc chữ. Phân vai theo `employees.position` + tổ.

**D. Thứ tự dựng + trạng thái thật (đừng tô hồng)**
- **A** nền phòng ban ✅ · **B** routing_step sửa được ✅ · **C** tổ view ✅ *(build + browser-verified
  2026-07-18)* · **D** giao nhận 2 chiều + phiếu in + realtime đích danh ← **TIẾP**.
- **Chunk C đã làm THẬT:** BE step transitions bắt đầu/hoàn thành (cổng đến-lượt tuyến tính) + bảng tổ
  (đếm đến-lượt/đang chạy) + lệnh-của-tổ; FE `TheoDoiSanXuatView` 3 tầng (cây tổ → lệnh → thẻ routing
  thực thi). 629 test pass, tsc 0, click-through verify (bắt đầu→hoàn thành→board cập nhật).
- **Chunk C CÒN HOÃN / GAP (phải nhớ, đừng tưởng đã xong):**
  - Realtime hiện là **broadcast + FE lọc `to_id`, CHƯA publish "đích danh" theo tổ→user** (→ D).
  - "Quét QR" ở màn thực thi hiện là **nút bấm màn tổ trưởng + khối QR trang trí** (chưa sinh QR thật).
    Màn thợ textless (`NhapLieuXuongView`) **chỉ ghi sản lượng, CHƯA điều khiển routing** → 2 cơ chế
    song song, chưa nối.
  - Giao nhận 2 chiều (`so_nhan` + phiếu in + ký) **chưa làm** (→ D). "Xong bước → đến lượt tổ kế" hiện
    chỉ đổi trạng thái, chưa có phiếu bàn giao.

## 1. Phạm vi & mục tiêu
Đóng khâu **đơn chốt → chuẩn bị sản xuất → phát xuống xưởng**, chủ sở hữu = bộ phận **Kế hoạch sản xuất**:
```
Đơn chốt → (tự đề Lệnh SX nháp) → bung tờ in · GHÉP BÀI · gán máy · duyệt mẫu · kế hoạch vật tư → PHÁT theo tờ in → tổ chạy
```
KHÔNG làm: bình bài tự động (auto-imposition — việc chế bản trong phần mềm dàn trang), điều độ lịch máy chi tiết, APS, MRP tự động.

## 2. Ba tầng — cardinality khóa đúng từ đầu
| Tầng | Là gì | Quan hệ |
|---|---|---|
| **Đơn** | khách mua gì · cọc · giao · công nợ | 1 đơn **1–n** lệnh |
| **Lệnh SX** | **1 ấn phẩm/cấu phần in = 1 routing** (ruột · bìa · name card · tem) — traveler qua các tổ | thuộc 1 đơn · móc **n–n** với tờ in |
| **Tờ in** | 1 lượt chạy máy vật lý (1 bộ kẽm · 1 lần canh) — **nơi ghép** | **n–n** với lệnh qua *danh sách xếp bài* + số con |

- Chốt đơn → tự sinh **các lệnh nháp: mỗi ấn phẩm 1 lệnh** (catalogue 2 phần = 2 lệnh). Idempotent theo đơn.
- Ví dụ chuẩn: **3 đơn → 4 lệnh → 2 tờ in** (đơn An tách ruột/bìa; tờ #5 ghép bìa-An + Bình + Cường; tờ #7 riêng ruột-An).
- 1 lệnh có thể trải **>1 tờ** (ruột 32 trang = 2 tay = 2 tờ) → tờ ↔ lệnh **n-n cả hai chiều**.
- **Lệnh đọc quy cách / routing từ PTG** qua cầu `OrderLine.phieu_thanh_phan_id` — không nhập lại.

## 3. Ghép bài (trọng tâm) — MÁY CHỈ GHI NHẬN
**Là gì:** bộ phận kế hoạch **tự chọn** các lệnh in được cùng nhau → kéo lên **1 tờ in** → **gõ số con** mỗi lệnh. Máy **ghi lại** placement.
- Máy **hiển thị sẵn** giấy / khổ / màu của mỗi lệnh (đọc từ PTG) cho người dễ nhìn. **KHÔNG** lọc / chặn / cảnh báo dư-thiếu — mọi phán đoán (ghép cái gì với cái gì, số con bao nhiêu) để **người kế hoạch**.
- **Danh sách xếp bài (placement)** = nguồn sự thật: mỗi dòng *tờ · lệnh · số con*. Đây là "cái bóng kế toán" của ghép — KHÔNG phải layout dàn trang.
- Điều kiện "ghép được" (cùng giấy + khổ + số màu) là **kiến thức của người kế hoạch**, không phải luật máy enforce.

Ví dụ tờ #5 (người kế hoạch tự cân số con theo nhu cầu):

| Lệnh | Đơn | Con/tờ |
|---|---|---|
| Bìa catalogue | An | 2 |
| Name card | Bình | 4 |
| Tem | Cường | 1 |

## 4. Routing theo LỆNH — trước in / sau in
Mỗi lệnh có **đúng 1 routing** (đọc từ PTG `PhieuThanhPham`, thứ tự `thu_tu`); mỗi bước bắn về **tổ** (map qua `cong_doan.department_id`). Ranh giới chung/riêng = **IN + xén rời**:

| Giai đoạn | Công đoạn | Chủ |
|---|---|---|
| Trước in | file + **duyệt mẫu** | **Lệnh** (mỗi ấn phẩm) |
| Trước in | xuất **kẽm** (CTP) | **Tờ in** (1 bộ cả tờ) |
| In | canh máy + chạy | **Tờ in** |
| ⎯ *xén rời bài* ⎯ | | ranh giới |
| Sau in | cán / UV *toàn tờ* (nếu cùng y/c) | Tờ in (tới xén) |
| Sau in | bế · gấp · dán · cắt TP | **Lệnh** (tổ riêng · thuê ngoài riêng) |
| Hoàn thiện | ráp cấu phần (bìa + ruột) | trong **1 đơn** (Tổ thành phẩm / KCS) |

**Ánh xạ 8 tổ SVN:** Tổ kỹ thuật (kẽm) + Tổ in = cấp **tờ in**; Tổ cắt / cán / bồi / bế / dán / thành phẩm-KCS = cấp **lệnh** (theo routing); Tổ giao hàng = cấp **đơn**.

## 5. Luồng thao tác (bộ phận kế hoạch)
1. **Đơn chốt → lệnh nháp tự tạo** (mỗi ấn phẩm 1 lệnh), vào hàng "chờ kế hoạch".
2. **Bung tờ in cần chạy** — đọc giấy / khổ / màu / số con từ PTG.
3. **Ghép bài** (§3) — chọn lệnh → xếp lên tờ + gõ số con. Lệnh không ghép → tờ riêng.
4. **Gán máy** từng tờ in.
5. **Duyệt mẫu** — tick per lệnh; minh chứng (ảnh Zalo / scan) **tùy chọn**; **con dấu** người + giờ + snapshot `{tổ · chức vụ · tên}` đóng băng.
6. **Kế hoạch vật tư** (§7) — nhìn cần / tồn, xin mua phần thiếu.
7. **Phát theo tờ in** — cổng mở khi tờ **đã gán máy + MỌI lệnh trên tờ đã duyệt mẫu (AND)**. Giấy khách ứng chưa về = cảnh báo mềm. Thợ nhận **1 phiếu / tờ in**; sau xén, finishing bắn về tổ theo từng lệnh.

## 6. Chi phí (bản tối thiểu)
- **Tầng tờ in** (giấy · kẽm · công canh · bù hao makeready) → chia về **từng lệnh theo số con** (share = con_lệnh ÷ tổng con tờ) → cộng lên đơn.
- **Tầng lệnh** (gia công sau xén · running waste) → tính **thẳng vào lệnh / đơn**, KHÔNG chia share.
- Bù hao 2 cấp: makeready = của tờ · running/finishing = của lệnh (DOMAIN §31).
- **LÀM NGAY:** ghi *số con mỗi placement* (không tái tạo được sau). **ĐẨY SAU:** phép tính phân bổ / quyết toán · hủy-giữa-tờ.

## 7. Kế hoạch vật tư — MÁY CHỈ GHI NHẬN (màn nhìn + nút xin mua)
Máy **đọc + tổng hợp + hiển thị**; người **quyết mua**; máy **ghi phiếu**.
```
Lệnh + tờ in → máy tổng hợp NHU CẦU (đọc PTG):  Giấy (theo tờ) · Mực/màng/keo (theo lệnh, PhieuVatTu)
             → đối chiếu TỒN (đọc Kho) → hiện:  Cần · Tồn · Thiếu
             → Thiếu: người bấm "Tạo phiếu xin mua" → luồng MUA HÀNG (sẵn có)
```
- **Kho:** chỉ **ĐỌC tồn**, **KHÔNG khóa / giữ chỗ** (domain: tồn hiện, cảnh báo mềm). Xuất vật tư thật khi chạy → phiếu xuất kho sẵn có.
- **Mua hàng:** phần thiếu → **phiếu xin mua (nháp)** đẩy vào YCMH đã có. Máy không tự mua.
- **KHÔNG:** MRP tự động · tự đặt mua · min-max reorder · reserve tồn — trừ khi xin sau.
- Ghi chú: giấy thường mua riêng theo lệnh; mực / hóa chất là hàng kho thường xuyên → "thiếu → mua" chủ yếu rơi vào giấy.

## 8. Tổ chạy (sản lượng · bàn giao · QC) · Trạng thái · Kết thúc lệnh
**Trạng thái (suy ra, không bấm tay):** Tờ in: chờ ghép → đủ điều kiện → **Phát** → in xong. Lệnh: Nháp → đang chạy (theo routing) → **xong**. Đơn: suy từ các lệnh. Cổng cứng: **chỉ từ "Phát" (tờ in) mới cho xuất kho / ghi sản lượng.**

**Sản lượng & bàn giao (tổ chạy) — MÁY CHỈ GHI NHẬN:**
- Mỗi công đoạn: **tổ trưởng** ghi sản lượng = **số đạt + số hỏng** (gắn lệnh · công đoạn · tổ). Máy lưu — **log, không state-machine**.
- **Bàn giao:** xong công đoạn, tổ trưởng **giao** số đạt sang công đoạn / tổ kế → **[REAL-TIME]** tổ kế **xác nhận nhận**. Máy ghi giao + nhận (lệch số để sau truy).
- Tiến độ lệnh **suy ra** từ các bản ghi này. Máy **KHÔNG** tính khoán ở đây — khoán (số đạt × đơn giá) = **P2**, đọc lại số từ đây.

**Kết thúc lệnh = NHẬP KHO THÀNH PHẨM:**
- SP nhiều cấu phần → có lệnh **"đóng cuốn / ráp"** (đã là 1 `PhieuThanhPhan` trong PTG: *ruột / bìa / đóng cuốn*) hợp ruột + bìa thành thành phẩm bán được.
- Sản xuất xong (đóng cuốn + KCS đạt) → **[người] tạo YÊU CẦU NHẬP KHO TP theo ĐƠN HÀNG** (gom thành phẩm của đơn) → Kho nhận hàng thực → **nhập kho** (luồng Kho sẵn có).
- Máy **suy**: đủ SL thành phẩm nhập kho ⟹ lệnh / đơn **XONG**. Nút "tạo yêu cầu nhập kho" **chỉ bật khi *done***; **không bấm "xong" tay** — đóng khi có phiếu nhập kho.
- Không đạt / thiếu SL → nhánh **in bù** (chi tiết P1). Máy KHÔNG enforce trình tự ruột → đóng cuốn (tổ tự biết) — chỉ ghi tiến độ + nhập kho.

**QC ghi lỗi — MÁY CHỈ GHI NHẬN (QC nêu → TỔ TRƯỞNG xác nhận → mới ghi):**
- QC (đột xuất **bất kỳ công đoạn nào**) hoặc KCS (cuối): tạo **phiếu lỗi** = ảnh + **tổ bị quy** + công đoạn + mô tả → trạng thái *chờ xác nhận*.
- **[REAL-TIME]** tổ trưởng tổ bị quy nhận thông báo NGAY → **XÁC NHẬN** → lỗi mới **ghi nhận chính thức**. Chưa xác nhận = chưa thành lỗi chính thức.
- Máy chỉ ghi 2 bước + đẩy thông báo; **KHÔNG** tự quy lỗi / trừ khoán / quyết in bù — hậu quả để **người** xử lý (P1). Ghi từ ngày 1 để sau có dữ liệu.

### 8.1 Mở rộng khi build — Chunk 2 (services record-only, 2026-07-18)
> Phần spec chưa nói rõ, agent tự quyết theo domain in offset khi dựng
> `services/lenh_san_xuat_service.py`. (Chi tiết + lý do: `BUILD-ke-hoach-san-xuat.md` §GIẢ ĐỊNH.)
- **Bung IDEMPOTENT theo (đơn · ấn phẩm)** (rõ hoá §2/§5.1): mỗi lần bung chỉ tạo lệnh cho ấn phẩm
  (`phieu_thanh_phan_id`) CHƯA có lệnh. Chốt lại không nhân đôi. Đơn `cancelled` → không bung.
  `may_id` lệnh = gợi ý `PhieuThanhPhan.may_id` (máy chạy THỰC gán ở tờ in).
- **Sửa xếp bài sau khi phát = CHẶN** (bổ sung §3): thêm/sửa/xoá placement chỉ khi tờ *chờ ghép* /
  *đủ điều kiện*. Tờ *đã phát* / *in xong* (đã xuống xưởng) → in bù / hủy (P1). Cổng toàn vẹn
  trạng thái, KHÔNG phải "máy phán ghép cái gì".
- **Trạng thái tờ in suy ra tự động** (rõ hoá §8): *chờ ghép ⇄ đủ điều kiện* tính lại sau
  ghép/gán máy/duyệt mẫu/sửa placement; không hạ cấp khi *đã phát*. `phat` (cổng AND §7) → tờ *đã
  phát* + mọi lệnh nháp trên tờ → *đang chạy*. `in xong` chưa tự suy ở P0 (thiếu tín hiệu) — cổng
  cứng dùng *đã phát*.
- **Cổng cứng sản lượng / bàn giao** (cụ thể hoá §8) = lệnh phải *đang chạy* (đã phát) hoặc *xong*.
- **Idempotent mốc thời gian**: duyệt mẫu đã duyệt → giữ con dấu + snapshot đầu (đóng băng); xác
  nhận nhận / tổ trưởng xác nhận QC đã xác nhận → giữ mốc đầu.
- **Nhập kho thành phẩm → suy XONG** (rõ hoá §8): đích "đủ SL" = `OrderLine.qty` của ấn phẩm (lùi
  `PhieuThanhPhan.so_luong`). `nhap_kho_thanh_pham(lenh, so_luong_nhap)` nhận TỔNG SL đã nhập kho
  (caller cộng dồn từ phiếu Kho THẬT — chưa nối API Kho); `≥ đích` ⇒ lệnh *xong*. KHÔNG thêm cột
  cộng-dồn ở `lenh_sx`.
- **Đơn "xong sản xuất" = SUY RA** (`order_production_done` = có ≥1 lệnh & mọi lệnh không-hủy đều
  *xong*). KHÔNG ghi `orders.status` (Order module sở hữu; chưa có trạng thái "xong SX" — không
  thêm để khỏi đụng `order.py`/migration).
- **Hủy lệnh** (`huy_lenh`): đánh dấu *hủy*, GIỮ log sản lượng/bàn giao/QC; chặn hủy khi đã *xong*.
  Hủy-giữa-chừng chi tiết (rollback/quyết toán) = P1.

### 8.2 Mở rộng khi build — Chunk 3 (API: schemas + routers + SSE, 2026-07-18)
> Tầng API mở đúng các thao tác §5–§8 qua `routers/lenh_san_xuat.py` (prefix `/api/lenh-sx`), gọi
> `LenhSanXuatService`. Map lỗi service → HTTP: `NotFound`→404 · `ValidationError`→422 (cổng phát
> chưa đủ điều kiện) · `Conflict`→409 (cổng cứng: chưa phát mà ghi sản lượng, đơn hủy, lệnh xong…).
> (Chi tiết + lý do: `BUILD-ke-hoach-san-xuat.md` §GIẢ ĐỊNH.)
- **Bung = GỌI TAY** `POST /api/lenh-sx/lenh/bung {order_id}` (KHÔNG tự chạy khi chốt đơn — tránh
  đụng `order.py`/luồng Đơn hàng bán). Idempotent nên bấm lại an toàn; FE gọi khi vào màn kế hoạch.
- **RBAC = module `san_xuat`** ("Sản xuất", đã có trong catalog quyền — KHÔNG thêm module mới).
  Action-level dùng bit chung: `read` (đọc) · `create` (bung/ghép/thêm placement/ghi sản lượng/bàn
  giao/QC nêu lỗi) · `update` (gán máy/sửa-xoá placement/xác nhận nhận/tổ trưởng xác nhận QC) ·
  `approve` (duyệt mẫu + **phát**) · `cancel` (hủy lệnh) · `manage_status` (nhập kho đóng lệnh).
  **Tách vai công nhân chi tiết (thợ/tổ trưởng/QC/kho) = DEFER** — seed RBAC chưa có các vai công
  nhân riêng; khi có sẽ cấp tập con các action-bit trên (hoặc tách module `ke_hoach_sx` riêng).
- **Actor lấy TỪ TOKEN** (người ghi sản lượng = `user.id`; người duyệt mẫu = `user.id` → snapshot
  con dấu). KHÔNG nhận `actor_id`/`nguoi_ghi` qua body (chống mạo danh).
- **Real-time (SSE) = broadcast tín hiệu NHẸ qua hub in-process CHUNG** (`app/realtime.py`) — client
  giữ 1 kết nối `/api/quotations/events` nhận MỌI loại sự kiện, lọc theo `type`. Mốc đẩy: `lenh_sx_
  duyet_mau` · `lenh_sx_phat` (kèm `lenh_ids`) · `lenh_sx_ban_giao` (kèm `to_nhan_id`) · `lenh_sx_qc_
  loi` (kèm `to_bi_quy_id`). Payload chỉ là tín hiệu; số/liệu chính xác FE refetch. **Đẩy ĐÍCH DANH
  theo tổ (resolve tổ→user_id rồi `hub.publish`) = refinement Chunk 8 (màn thợ)** — hiện broadcast +
  FE lọc theo tổ là đủ real-time (bám đúng cách `orders.py` broadcast `order_pending_changed`).
- **DTO đọc**: `GET /lenh` (list) + `GET /lenh/{id}` (detail: tờ in + log sản lượng/bàn giao/QC +
  đích SL & Σ đạt) nuôi màn tracking; `GET /forms` + `GET /forms/{id}` (placements + lệnh trên tờ)
  nuôi màn ghép/theo máy; `GET /lenh/{id}/san-luong` đọc log. Helper đọc thêm ở service (append-only,
  không đổi logic mutate Chunk 2).

## 9. Phân định trách nhiệm
- **Đơn bán (Sale):** chốt · khóa · đẩy; chỉ hiển thị + link. KHÔNG thấy / đụng ghép bài.
- **Kế hoạch SX:** bung tờ in · **ghép bài** · gán máy · duyệt mẫu · **kế hoạch vật tư** · phát.
- **Tổ:** xếp người · chạy công đoạn · ghi sản lượng · QC.

## 10. Ranh giới (không phình)
- KHÔNG **auto-imposition** — dàn bài là việc chế bản trong phần mềm dàn trang; ERP chỉ ghi số con. PTG đã có "gợi ý số con / khổ" → đọc lại.
- KHÔNG đụng **engine tính giá** (báo giá per-đơn giữ nguyên; chỉ quyết toán mới chia chi phí thực về lệnh).
- KHÔNG đụng **màn Đơn hàng bán**.
- **TÁI DÙNG:** `routing_engine` (`compute_kem` — số tay *tự-trở-aware*, KHÔNG tự tính màu × mặt) · `cong_doan.department_id` · `piece_work` (khoán) · Kho · Mua hàng.

## 11. Cấu trúc dữ liệu (mức thiết kế — schema chi tiết viết khi "làm đi")
**Nền ĐỌC — đã có sẵn (verify 2026-07-18):**
- `PhieuThanhPhan` (= ấn phẩm): giấy `giay_id` / khổ `kho_in_*` / số màu `so_mau_a,b` / **`so_con`** / `may_id`. → nguồn của **Lệnh**.
- `PhieuThanhPham` (finishing): `thu_tu` · `cong_doan_id` → tổ · `nha_cung_cap`. → **routing**.
- `PhieuVatTu` (mực / màng / keo) + giấy → **nhu cầu vật tư**.
- `OrderLine.phieu_thanh_phan_id` → **cầu đơn ↔ ấn phẩm** (đã pin sẵn) → bung = duyệt `order.lines`.

**Xây mới (P0):**
- **Lệnh SX**: thuộc đơn · FK `phieu_thanh_phan_id` · trạng thái · cụm duyệt mẫu (`approved_at/by` + snapshot).
- **Tờ in** (`print_form`): giấy · khổ · số màu · `may_id` · số tờ chạy · số kẽm · trạng thái phát.
- **Danh sách xếp bài** (`gang_placement`): FK tờ in · FK lệnh · **số con**.
- **Phiếu lỗi QC** (`qc_defect`): FK lệnh · công đoạn · **tổ bị quy** · ảnh · mô tả · **trạng thái xác nhận** (QC nêu → tổ trưởng xác nhận). Record-only; disposition để P1.
- **Sản lượng** (`san_luong`): FK lệnh · `cong_doan_id` · tổ · **số đạt · số hỏng** · người ghi (tổ trưởng) · thời điểm — log.
- **Bàn giao** (`ban_giao`): FK lệnh · công đoạn *từ → tới* · số giao · tổ giao → tổ nhận · giao_at · **nhan_at (xác nhận)** — record-only.

**Bẫy DB (BẮT BUỘC):** KHÔNG Alembic — thêm bảng/cột phải viết `db_migrations.py` + cập nhật `DB_SCHEMA.md` (có guard test). Boolean `server_default` phải bool (`false` / `true`). Bảng mới `create_all` tự tạo; đổi cột bảng cũ phải migration.

## 12. Roadmap phân pha
| Pha | Nội dung |
|---|---|
| **P0 — làm ngay** | 3 tầng đơn / lệnh / tờ in · placement + **số con** · bung · ghép (record-only) · gán máy · duyệt mẫu AND · phát theo tờ · xuất giấy theo tờ · **kế hoạch vật tư (màn nhìn + nút xin mua)** · **sản lượng/công đoạn (tổ trưởng) + bàn giao (giao→nhận)** · **QC ghi lỗi (QC → tổ trưởng xác nhận, real-time)** · **yêu cầu nhập kho TP theo đơn → đóng lệnh** |
| **P1** | phân bổ chi phí theo share · hủy-giữa-tờ · **xử lý lỗi / disposition (trừ khoán · in bù · đòi NCC, fault_party)** · quyết toán lời / lỗ per lệnh |
| **P2** | khoán chia tổ (nối `piece_work`) · điều độ lịch máy |

## 13. Mở rộng thiết kế — Tổ sản xuất · Routing sửa được · Giao nhận 2 chiều
> Chốt **2026-07-18** qua thảo luận đa vai (chủ xưởng · kế hoạch · tổ trưởng · thợ). Bổ sung cho
> §2/§4/§5/§8. **CHƯA code** (trừ nền phòng ban đang dựng). KIM CHỈ NAM giữ nguyên: máy chỉ ghi nhận,
> người quyết. Lý do gốc: chủ xưởng phải NHÌN được xưởng đang làm gì + phải đủ điều kiện mới sản xuất —
> nên module xây TỪ TRÊN (giám sát/tổ) xuống, không phải từ màn nhập liệu của thợ.

### 13.1 Phòng ban SẢN XUẤT = đánh dấu, lấy cả cây con
- Thêm cột **`departments.la_san_xuat`** (Boolean, default false). Tick ở **form sửa Phòng ban** (màn
  RBAC/phòng ban đang có — KHÔNG đẻ màn mới).
- **"Là sản xuất" (effective) = tự nó tick HOẶC có tổ tiên tick** — kế thừa xuống cả subtree qua
  `parent_id`. Tick 1 lần ở nhánh gốc ("Sản xuất") → cả cây tổ con thành sản xuất. KHÔNG cascade lưu —
  tính bằng đi ngược cây (một nguồn sự thật).
- Phân hệ Sản xuất **liệt kê đúng subtree được tick, HIỂN THỊ DẠNG CÂY** (phòng cha → tổ con). Bấm 1 tổ
  → lệnh của tổ.
- Nền dữ liệu đi kèm (seed + cấu hình thật): dưới "Sản xuất" tạo các **tổ** cấp `unit_levels`="Tổ"
  (Chế bản · In offset · Cán màng · Bế/Xén · Đóng gói · KCS), mỗi tổ có **tổ trưởng = `head_user_id`**;
  **gắn `cong_doan.department_id` → đúng tổ**; **xếp thợ về đúng tổ** (`employees.department_id`, chuyển
  khỏi HCNS ở demo hiện tại).

### 13.2 Routing của lệnh = BẢN SAO từ job spec, kế hoạch SỬA được
- Khi **bung lệnh**: routing = **copy các công đoạn từ job spec tính giá** (`PhieuThanhPham`, thứ tự
  `thu_tu`) thành **routing RIÊNG trên lệnh** (`routing_step` — instance per job, đúng "TẦNG 2" mà
  `cong_doan.py` ghi "chưa dựng"). KHÔNG trỏ sống vào PTG → sửa routing lệnh **không đụng bảng giá**.
- Mỗi bước: `cong_doan_id` · thứ tự · **tổ phụ trách** (mặc định = `cong_doan.department_id`, sửa được)
  · trạng thái (chờ/đang/xong).
- Bên **kế hoạch sửa routing** (thêm/bớt/đổi thứ tự/đổi tổ) **khi lệnh còn bước kế hoạch (trước Phát)**.
  Đã phát → **khóa các bước đã/đang chạy**, chỉ cho sửa bước **chưa tới lượt** (cổng toàn vẹn trạng thái,
  không phải máy phán).

### 13.3 Phát = bắn lệnh về đúng các tổ trong routing
- Kế hoạch setup xong (ghép · gán máy · duyệt mẫu · routing chốt) → **Phát** → lệnh hiện trong
  **"danh sách tổ → lệnh của tổ"** của **mỗi tổ có công đoạn trong routing** (không bắn tổ ngoài routing).
- Tổ đến lượt theo thứ tự routing.

### 13.4 Màn tổ THỰC THI (đẩy xuống tổ)
- Vào từ **Theo dõi SX → cây tổ → tổ → lệnh của tổ**. Màn thực thi (tham khảo ảnh chủ gửi): **routing
  dạng thẻ** (mỗi công đoạn 1 thẻ: chờ/đang/xong + nút Bắt đầu/Hoàn thành **qua quét QR**), công nhân đang
  vận hành, nhật ký live, phiếu dán, BOM.
- Tổ thấy **nguyên lệnh + routing**; chỉ **thẻ công đoạn của tổ mình** thao tác được, bước khác chỉ xem.
  "Đến lượt" = bước hiện hành thuộc tổ.
- Màn **thợ textless** (tablet ở máy) = biến thể cùng luồng: quét QR → 1 việc đến lượt + nút to, không
  đọc chữ. Phân vai thợ/tổ trưởng theo `employees.position` + tổ.

### 13.5 Giao nhận 2 CHIỀU + phiếu in + real-time "đến lượt"
- Cụ thể hoá §8: bàn giao ghi **2 số** — tổ giao ghi **`so_giao`**, tổ nhận xác nhận **`so_nhan`** —
  **lệch được**. Máy hiện **chênh lệch = so_giao − so_nhan**, KHÔNG phán ai sai; lý do chênh **ghi tay
  trên phiếu**. (Thêm cột **`ban_giao.so_nhan`**.)
- **Phiếu bàn giao IN ĐƯỢC**: lệnh · sản phẩm · tổ giao → tổ nhận · công đoạn · số giao / số nhận / chênh
  · 2 ô ký (giao/nhận) · QR.
- **Real-time**: tổ A **hoàn thành công đoạn** → **đẩy ĐÍCH DANH tới tổ B** (tổ của bước kế trong routing)
  "đến lượt" — nâng cấp broadcast §8.2 thành publish theo `to → user_id`. Tổ B "ting" → sang tổ A lấy hàng.

### 13.6 Thứ tự dựng
- **A. Nền phòng ban** (13.1) — ✅ XONG + browser-verified (cờ `la_san_xuat` self/ancestor; seed 6 tổ
  dưới "Sản xuất"; gắn công đoạn→tổ + chuyển thợ khỏi HCNS; checkbox form Phòng ban; migration `0075`).
- **B. Routing_step** (13.2) — ✅ XONG + browser-verified. Bảng `routing_step` create_all; **copy từ
  `PhieuThanhPham`** khi bung, tổ = snapshot `cong_doan.department_id`; API get/thêm/sửa/xóa/reorder
  (khóa bước ≠`cho` + reorder chỉ nháp) — 11 test. **KIM CHỈ NAM (chốt cứng): kế thừa từ tính giá =
  giá trị MẶC ĐỊNH; ở màn LỆNH (CẤU HÌNH) PHẢI cho SỬA — không read-only.** Công đoạn→tổ có DEFAULT ở
  module Công đoạn (ô "Phòng ban/Tổ phụ trách"; `/api/cong-doan/phong-ban` **lọc về tổ SX** `la_san_
  xuat`); routing DEFAULT do Loại SP/Tính giá gán. Panel routing = **traveler timeline** (`.lsx-trav`,
  ui-ux-pro-max + styleseed) — **nháp: sửa được** (đổi tổ/thứ tự/thêm-bớt, dropdown tổ lọc tổ SX);
  đang chạy/xong: read-only (trạng thái qua QR).
  **Màn LỆNH = 2 chế độ**: NHÁP = **CẤU HÌNH** (routing sửa được · tờ in/ghép · gán máy · duyệt mẫu +
  nút **PHÁT HÀNH LỆNH**, ẩn khối runtime) ↔ ĐANG CHẠY/XONG = **THỰC THI** (sản lượng/giao nhận/QC/
  tiến độ). Phát hành = phát tờ in đủ đk → lệnh đang chạy → tổ trong routing nhận (realtime, chunk C/D).
- **C. Tổ view** (13.3–13.4) — ✅ XONG + browser-verified (2026-07-18). Cây tổ (`/api/lenh-sx/to-board`,
  đếm đến-lượt/đang chạy, dồn con→cha) → lệnh của tổ (`/api/lenh-sx/to/{id}/lenh`, đến-lượt lên đầu) →
  màn thực thi `TheoDoiSanXuatView` (thẻ routing chờ/đang/xong; chỉ bước ĐẾN LƯỢT của TỔ MÌNH mới
  Bắt đầu/Hoàn thành). BE `bat_dau_buoc`/`hoan_thanh_buoc` (cổng đến-lượt tuyến tính + lệnh dang_chay).
  Realtime = broadcast `lenh_sx_routing` (FE lọc `to_id` → "ting"). **GAP → D:** publish ĐÍCH DANH
  (tổ→user) chưa có; QR ở màn thực thi mới là nút + khối trang trí (chưa QR thật, chưa nối màn thợ
  textless vốn chỉ ghi sản lượng). Xem **§0 "Chunk C còn hoãn/gap"**.
- **D. Giao nhận 2 chiều + phiếu + realtime đích danh** (13.5). ⬅ TIẾP.
