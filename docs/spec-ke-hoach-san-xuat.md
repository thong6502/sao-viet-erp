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
