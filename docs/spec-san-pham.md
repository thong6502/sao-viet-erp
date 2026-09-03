# SPEC — MODULE SẢN PHẨM (Product · JobSpec)

> **2 tầng:** `loai_san_pham` (template tái dùng, **gán quy tắc bình bài**) + `jobspec` (đặc tả cụ thể trên 1 báo giá).
> Cấp cho engine: khổ, số trang, số màu/mặt, binding, dieline → để bình bài + tính giá.
> Anh em với `spec-quy-tac-binh-bai.md`, `spec-may-thiet-bi.md`, `spec-cong-doan.md`.

> **Đối chiếu code (09/2026), chỉ soát §2 tầng 1:** hai trường `default_so_mat` và `vat_rate`
> KHÔNG tồn tại trong model thật (`backend/app/models/loai_san_pham.py:42-68`) — đã sửa lại ở bảng
> §2 bên dưới. `imposition_rule_id` cũng **không bắt buộc** (NULL được, chốt MVP cố tình không
> hard-block), dù trỏ tới bảng `quy_tac_binh_bai` — bảng này **không tồn tại** trong hệ (không
> model, không màn khai — `backend/app/services/catalog_excel_specs.py:232-234`); trường chỉ lưu
> số nguyên chờ sẵn cho tương lai. **Tầng 2 `jobspec` (§3 trở xuống) chưa được đối chiếu code trong
> đợt rà soát này** — đọc như tài liệu thiết kế/dự kiến, không phải mô tả hiện trạng đang chạy;
> trong Phiếu tính giá thực tế, chỉ `ten` và `routing_template` của Loại sản phẩm thật sự chảy vào
> `PhieuThanhPhan` (`frontend/src/pages/PhieuTinhGiaDetailView.tsx:1327-1349`).

---

## 1. Tổng quan

### 1.1 Hai tầng — đừng gộp
| Tầng | Là gì | Master? |
|---|---|---|
| **Loại sản phẩm** | Template (name card, sách, hộp…), **gán rule bình bài + routing mặc định + VAT** | ✓ Master |
| **JobSpec** | Giá trị cụ thể trên 1 dòng báo giá (khổ, SL, giấy, màu…) | Per báo giá |

> Cái **gán vào quy tắc bình bài** là **Loại sản phẩm** (`imposition_rule_id`), không phải từng job.

### 1.2 Trách nhiệm
- Khai **cái gì cần in** (khổ TP, số trang, số màu/mặt, binding, dieline, giấy).
- Trỏ **rule bình bài** + **routing template** + **VAT** để engine biết xếp kiểu gì, làm bước nào, thuế bao nhiêu.

### 1.3 KHÔNG làm gì
- Không giữ cách xếp → **Quy tắc bình bài**. Không giữ khổ máy/nhíp → **Máy**.
- Không tự tính tiền — chỉ feed spec cho **engine**.

---

## 2. Mô hình dữ liệu — TẦNG 1: `loai_san_pham`

Bảng dưới đã sửa theo model thật (`backend/app/models/loai_san_pham.py:42-68`) — xem callout đầu
file cho phần đã bị bỏ.

| Field | Kiểu | Bắt buộc | Default | Mô tả |
|---|---|---|---|---|
| id | PK | ✓ | | |
| ma | string(30) unique | ✓ | | |
| ten | string(150) | ✓ | | |
| structural_type | enum(flat, multipage, box, label) | ✓ | | quyết nhánh spec + tương thích rule (§5) |
| box_sub_type | enum(folding_carton, corrugated, rigid) | khi box | | quyết máy đủ điều kiện + routing |
| imposition_rule_id | FK → quy_tac_binh_bai *(bảng đích không tồn tại — chỉ lưu số nguyên)* | Không | NULL | rule bình bài, chờ sẵn |
| has_cover | bool | | false | có bìa riêng (multipage) |
| cover_type | enum(tu_bia, bia_roi) | khi has_cover | bia_roi | **tự bìa** dùng giấy ruột; bìa rời mới cần giấy bìa |
| default_binding | enum(ghim, keo, khau) | | | (multipage) |
| default_stock_class | enum(couche, ford, ivory, duplex, kraft) | | | |
| routing_template[] | FK[] → cong_doan | | | các công đoạn mặc định (in, cắt, cán, bế, đóng…) |
| ghi_chu | text | | | |
| active | bool | ✓ | true | |

**Đã bỏ khỏi bảng gốc (không có trong model thật):** `default_so_mat` (int 1/2 mặt) và `vat_rate`
(enum 5/8/10, thuế suất mặc định) — không trường nào trong hai trường này tồn tại ở
`loai_san_pham`. Thuế suất hiện được xử lý ở tầng Báo giá, không neo vào Loại sản phẩm.

---

## 3. Mô hình dữ liệu — TẦNG 2: `jobspec`

### 3.1 Chung (mọi structural_type)
| Field | Kiểu | Bắt buộc | Engine dùng | Mô tả |
|---|---|---|---|---|
| id | PK | ✓ | | |
| loai_san_pham_id | FK | ✓ | | → template §2 |
| so_luong | int | ✓ | Tất cả | SL thành phẩm đặt |
| so_mau_truoc | int | ✓ | Kẽm/lượt | số màu **process** mặt trước |
| so_mau_sau | int | ✓ | Kẽm/lượt | số màu process mặt sau (0 = trắng) |
| so_mau_pha_truoc | int | | Kẽm/lượt/mực | số màu **pha (spot)** mặt trước |
| so_mau_pha_sau | int | | Kẽm/lượt/mực | số màu pha mặt sau |
| danh_sach_mau_pha | json | | Mực | mã Pantone từng mặt (giá mực) |
| so_mat | int(1,2) | | Lượt | **flat**: khai rõ, hoặc suy `= (so_mau_sau>0 ? 2 : 1)` (§5) |
| giay_ruot_id | FK → tờ nguyên (Vật tư) | ✓ | Giấy | |
| may_in_id | FK → máy | | Bình bài+giá | chọn máy (hoặc để engine dò) |
| grain_requirement | enum(none, canh_dai, song_song_gay) | | Bình bài | ưu tiên cao hơn rule (§6) |
| finishing_chon[] | FK[] → cong_doan | | Công đoạn | override routing template |
| vat_rate_override | enum(5,8,10) | | | ghi đè VAT template |

> **Số màu/mặt (per-side) là gốc của kẽm & lượt:**
> `màu_mặt_trước = so_mau_truoc + so_mau_pha_truoc`; tương tự mặt sau. Passes & kẽm tính **theo từng mặt** (xem spec-cong-doan). Màu pha PHẢI tách theo mặt — 1 spot mặt trước không được đội số lượt/kẽm mặt sau.

### 3.2 Nhánh `flat` (name card, tờ rơi, poster) + **flat có gấp** (tờ gấp)
| Field | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| kho_tp_dai, kho_tp_rong | int(mm) | ✓ | khổ thành phẩm |
| bleed_mm | int | | mặc định 3 (ghi đè rule) |
| co_gap | bool | | tờ gấp (brochure gấp 3…)? |
| kho_mo_dai, kho_mo_rong | int(mm) | khi co_gap | **khổ mở (trải phẳng)** — dùng để BÌNH BÀI |
| fold_type | enum(bi, tri_C, gate, accordion, roll) | khi co_gap | kiểu gấp |
| so_nep | int | khi co_gap | số nếp gấp → công đoạn gấp |
| panel_widths | json | khi co_gap | bề rộng từng panel (panel trong hẹp ~1,5mm) |

> **tờ gấp** đứng giữa flat và multipage: bình bài dùng **kho_mo**, báo giá/giao hàng dùng **kho_tp** (đã gấp). Gấp là 1 công đoạn finishing.

### 3.3 Nhánh `multipage` (sách, catalogue) — RUỘT + BÌA tách riêng
**Ruột:**
| Field | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| kho_trang_dai, kho_trang_rong | int(mm) | ✓ | khổ 1 trang thành phẩm |
| so_trang | int | ✓ | số trang ruột (§5 quy tắc bội số) |
| binding | enum(ghim, keo, khau) | ✓ | quyết nested/gathered + creep + số bội |

**Bìa (sub-spec — chỉ khi has_cover):**
| Field | Kiểu | Mô tả |
|---|---|---|
| so_mau_bia_truoc, so_mau_bia_sau | int | màu bìa (thường khác ruột: bìa 4/4, ruột 1/1) |
| so_mau_pha_bia_truoc/sau | int | spot bìa |
| giay_bia_id | FK | **chỉ bắt buộc khi cover_type=bia_roi** (tự bìa dùng giấy ruột) |
| finishing_bia[] | FK[] | cán màng/ép kim… riêng bìa |
| tay_gap_bia | bool | bìa có tai gập không |

> **Bìa là 1 form bình bài RIÊNG** → sinh kẽm/tờ in riêng. Đây là gap lớn nhất của catalogue nếu gộp chung.
> **Gáy (spine)** suy ra: `spine = (số tờ ruột) × caliper_ruột` (caliper lấy từ **Vật tư**). Bìa keo: `rộng bìa mở = 2×kho_trang_rong + spine`.

### 3.4 Nhánh `box` (hộp) — 3D → engine TỰ SUY khổ trải
| Field | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| dai, rong, cao | int(mm) | ✓ | kích thước hộp **3D** (thành phẩm đã gấp) |
| kich_thuoc_kieu | enum(trong, ngoai) | | đo trong / ngoài |
| kieu_hop | enum(tuck_end, auto_bottom, RSC, rigid, custom) | ✓ | **kiểu cấu trúc** → quyết công thức khai triển |
| do_day_carton | int(µm) | ✓ | bù độ dày khi gấp |
| flap_glue_allowance | json | | chừa tai/keo (mặc định theo kiểu hộp) |
| dieline_id | FK → khuôn bế | | **tùy chọn** — chỉ khi ĐÃ có khuôn thật (tái dùng). **Hộp mới bỏ trống.** |
| flute | enum(E, B, C, BC…) | khi corrugated | loại sóng (trục cấu trúc riêng, ≠ thớ) |
| *(derived)* kho_trai_dai, kho_trai_rong | int(mm) | | **engine tự tính** — khổ trải phẳng để bình bài |

> **HỘP MỚI (chưa có khuôn):** engine **tự suy khổ trải** từ `dai×rong×cao + do_day + kieu_hop`, rồi bình bài + báo giá + vẽ **dieline preview**. Khi làm khuôn thật mới lưu `dieline_id` để lần sau tái dùng.
> Công thức khai triển (xấp xỉ, theo `kieu_hop`):
> ```
> tuck_end : kho_trai_rong = 2×(dai + rong) + tai_dan
>            kho_trai_dai  = cao + 2×(nắp gài ≈ rong)
> RSC      : kho_trai_dai  = 2×(dai + rong) + tai_dan
>            kho_trai_rong = cao + rong          (nắp trên + dưới, mỗi cái = rong/2)
> rigid    : tấm bồi trải + bù độ dày carton bồi
> ```
> **imposition hộp đọc `kho_trai` (suy hoặc từ khuôn), KHÔNG dùng kho thành phẩm 3D.**
> `box_sub_type` (§2) quyết **máy đủ điều kiện**: folding_carton→offset; B/C-flute→flexo/digital; rigid→offset+bồi+bế.

### 3.5 Nhánh `label` (tem nhãn) — cuộn hoặc tờ
| Field | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| kho_tem_dai, kho_tem_rong | int(mm) | ✓ | khổ tem thành phẩm |
| dang | enum(cuon, to) | ✓ | **cuộn** → repeat_around (flexo); **tờ** → step_repeat (decal offset) |
| web_width_mm | int | khi cuộn | khổ cuộn |
| gap_mm | int | khi cuộn | khe giữa tem |
| lanes | int/auto | khi cuộn | số làn ngang |
| core_size | enum(25,38,76) | khi cuộn | lõi (mm) |
| unwind_dir | enum | khi cuộn | chiều nhả |
| cut_type | enum(kiss, through) | | bế xuyên/không xuyên đế |
| facestock, liner | FK | | mặt in + đế (decal) |

---

## 4. Gang / ghép bài (nhiều mẫu 1 tờ) — ghi nhận, làm sau
JobSpec hiện là **1 mẫu**. Ghép nhiều name card/tem KHÁC nhau lên 1 kẽm cần **entity GangSheet** (mảng item, mỗi item khổ/SL/màu riêng, chia sẻ tờ in + kẽm, phân bổ chi phí theo diện tích/số con). **Không nhét vào JobSpec đơn** — để dành. `allow_gang` trên rule chỉ là "được phép ghép".

---

## 5. Quy tắc & validate

### 5.1 structural_type ↔ layout_mode = **ma trận tương thích** (không equality)
| structural_type | layout_mode được phép |
|---|---|
| flat | step_repeat, nesting (mẫu bất quy tắc: hang tag, sticker) |
| multipage | signature |
| box | nesting, step_repeat (blank chữ nhật) |
| label | step_repeat (decal tờ), repeat_around (cuộn) |

### 5.2 Số trang (multipage) phụ thuộc binding + pages_per_sig
```
ghim (saddle)  → so_trang bội 4
keo (perfect)  → so_trang bội 2 (cảnh báo nếu không bội pages_per_sig)
signature      → bội pages_per_sig (8/16/32) của rule
```

### 5.3 Bảng mã lỗi
| Code | Điều kiện | Loại |
|---|---|---|
| E-SP-MODE | structural_type không thuộc tập tương thích của rule | chặn |
| E-SP-BOX-STYLE | box thiếu kieu_hop (không suy được khổ trải) | chặn |
| E-SP-BOX-3D | box thiếu dai/rong/cao/do_day | chặn |
| E-SP-COVER | has_cover & cover_type=bia_roi & thiếu giay_bia_id | chặn |
| E-SP-LABEL | label=cuộn thiếu web_width/gap | chặn |
| W-SP-P4 | multipage ghim: so_trang không bội 4 (auto chèn trang trắng) | cảnh báo |
| W-SP-P2 | multipage keo: so_trang lẻ | cảnh báo |
| W-SP-PSIG | so_trang không bội pages_per_sig | cảnh báo |
| W-SP-FOLD | flat có gấp nhưng thiếu kho_mo | cảnh báo |
| W-SP-GRAIN | grain_requirement mâu thuẫn thớ giấy đã chọn | cảnh báo |

---

## 6. Ranh giới & seam
```
QUY TẮC BÌNH BÀI : cách xếp; SP cấp khổ TP/kho_mo/số trang/binding/dieline
MÁY              : khổ máy, nhíp, số units — SP không giữ
CÔNG ĐOẠN        : routing_template (template) → routing_step (job); finishing_chon override
VẬT TƯ (VAT_TU)  : giấy ruột/bìa (giá + CALIPER cho spine/creep) + mực (theo danh_sach_mau_pha)
KẼM & KHUÔN      : dieline_id (khổ trải hộp/tem)
BÁO GIÁ          : gom nhiều JobSpec line + overhead cty + margin + chiết khấu + bậc SL; VAT theo dòng (vat_rate)
THỚ (grain) — thứ tự ưu tiên: jobspec.grain_requirement > rule.grain_constraint > default;
              engine kiểm khớp thớ giấy đã chọn, chặn allow_rotate nếu vi phạm.
```

---

## 7. Seed data

> **Đối chiếu code (09/2026):** bảng dưới là dữ liệu MINH HOẠ lúc viết spec, không khớp mã seed
> thật. Seed thật (`LSP-0001..LSP-0008`) dùng mã tuần tự, không dùng mã gợi nhớ như bảng dưới, và
> cũng không có cột `rule`/`vat` (không tồn tại — xem callout đầu file): `LSP-0001` Name card,
> `LSP-0002` Tờ phơi/brochure gấp, `LSP-0003` Catalogue đóng keo, `LSP-0004` Sách đóng ghim,
> `LSP-0005` Hộp giấy Ivory, `LSP-0006` Thùng carton sóng, `LSP-0007` Tem decal cuộn, `LSP-0008`
> Thẻ nhân viên. Bảng dưới giữ lại làm ví dụ cấu trúc theo `structural_type`, không phải dữ liệu
> seed thật.

| ma | structural_type | rule | đặc trưng |
|---|---|---|---|
| NAMECARD | flat | PHANG-NUP | 90×53, Couché 300, 4/4, vat 8 |
| TORPHOI | flat (co_gap) | PHANG-NUP | A4 mở, gấp 3 (tri_C), 4/4 |
| CATALOGUE | multipage | SACH-KEO-16 | has_cover, bia_roi, binding=keo, ruột 4/4 bìa 4/4+cán, vat 5 |
| SACH-GHIM | multipage | SACH-GHIM-8 | binding=ghim, tự bìa, vat 5 |
| HOP-IVORY | box (folding_carton) | HOP-BE | dieline, ivory 350, vat 8 |
| THUNG-SONG | box (corrugated) | HOP-BE | flute B/C, routing flexo |
| TEM-DECAL | label (cuộn) | TEM-CUON | web 250, gap 3, core 76 |

---

## 8. Changelog — fix từ phản biện
1. **Box 3D**: thêm `dai/rong/cao/do_day_carton/flap` + `dieline_id` (khổ trải) + `box_sub_type/flute` (trước chỉ 2D → không tính được).
2. **Bìa multipage** = sub-spec riêng (màu/finishing/giấy/gáy) + `cover_type` tự bìa/bìa rời (trước gộp chung ruột).
3. **Spot per-side**: `so_mau_pha_truoc/sau` (trước 1 scalar → sai kẽm/lượt).
4. **Label** thêm khối cuộn (web/repeat/lanes/gap/core/cut_type) + `dang` cuộn/tờ (trước không báo giá được tem).
5. **Số trang** theo binding + pages_per_sig (ghim ÷4, keo ÷2, signature ÷pages_per_sig) — trước cứng ÷4.
6. **structural_type ↔ layout_mode** = ma trận tương thích (trước equality 1:1, chặn nhầm).
7. **so_mat** khai rõ hoặc suy `so_mau_sau>0` — làm rõ.
8. **Tờ gấp**: `kho_mo` (bình) vs `kho_tp` (gấp) + fold spec.
9. **Gáy (spine)** suy từ số trang × caliper (Vật tư).
10. **VAT** `vat_rate` theo Loại SP + override (5/8/10%).
11. **Thớ**: thứ tự ưu tiên jobspec > rule > default.
12. **Gang** nhiều mẫu = entity GangSheet riêng (ghi nhận, làm sau).
