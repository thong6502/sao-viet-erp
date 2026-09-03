# PRD — Danh mục **Thành phẩm** (hệ tự khai khi chốt đơn)

> Chốt 19/08/2026. Anh em với `prd-giao-hang.md` (§5 gọi sang đây) và `spec-san-pham.md`
> (KHÁC hẳn — xem §2).

> **Cập nhật 21/08/2026 (mg 0228) — công tắc đổi lần thứ 3, đọc trước khi tin §3/§5/§6/§8 bên
> dưới:** công tắc phân biệt Thành phẩm KHÔNG còn là `customer_id` mà là cột cờ riêng
> **`la_thanh_pham`** (Boolean). Kéo theo 3 thay đổi:
> - `customer_id` giờ chỉ còn là **vết nguồn gốc** (khách ĐẦU TIÊN đặt món này) — không còn là
>   chủ, không còn là công tắc chia màn, không còn là phạm vi gộp trùng, và **không bắt buộc**.
> - Khoá gộp trùng đổi từ `(khách hàng, tên đã chuẩn hoá)` xuống còn **chỉ tên đã chuẩn hoá**.
>   Hai khách đặt cùng tên hàng (vd "Hộp thuốc 10 vỉ") giờ **DÙNG CHUNG một dòng danh mục** thay vì
>   mỗi khách một dòng riêng.
> - Mã đổi từ `TP-<mã khách>-<nnn>` (đếm riêng theo từng khách) sang **`TP-00001…`** (đếm chung
>   toàn danh mục, không tái dùng số của dòng đã xoá).
>
> Lý do đổi (`thanh_pham_khai_bao.py:83-88`): *"thành phẩm là một cái TÊN HÀNG, nên khai để tái sử
> dụng, tránh phình lên"* — không còn là "hồ sơ sở hữu riêng của một khách" như 2 lần đổi trước.
> Nội dung §3/§5(L2,L5)/§6/§8 dưới đây giữ nguyên để lưu lịch sử quyết định 19/08; chỗ đã bị thay
> có chú thích ngay tại chỗ.

---

## 1. Vấn đề

Sản phẩm in là **hàng đặt riêng**. *"Hộp thuốc 10 vỉ — in 2 màu, cán bóng"* của khách A không có
sẵn ở danh mục nào, và sẽ không bao giờ có sẵn.

Nhưng kho **chỉ xuất được thứ CÓ trong danh mục** — luật siết 08/08/2026 bỏ ô tên tự do
(`stock_request_lines.ten_tu_do`) chính vì gõ tay thì sổ sách không tra được về đâu.

Hai câu trên đá nhau. Bản trước tôi giải sai: bắt người lập yêu cầu giao **"chọn mặt hàng kho"** —
tức là bắt họ chọn một thứ **chưa tồn tại**. Chủ dự án chặn đúng chỗ đó:

> *"Ví dụ đơn hàng là Hộp thuốc 10 vỉ — in 2 màu, cán bóng thì nó sẽ vào vật tư để thêm cái Hộp
> thuốc 10 vỉ — in 2 màu, cán bóng này chứ, sao lại Mặt hàng kho là sao"*

⇒ Không bắt ai chọn. **Hệ tự khai, đúng lúc đơn chốt.**

---

## 2. Cái này KHÔNG phải là gì

| Không phải | Vì sao |
|---|---|
| `loai_san_pham` (`spec-san-pham.md`) | Đó là **template cho engine** — name card / sách / hộp, gắn `imposition_rule_id` để bình bài + tính giá. Nó trả lời *"in kiểu gì"*, không phải *"hàng nào của đơn nào"*. |
| Một `hang_loai` thứ ba | Đo thật trước khi kết luận: 4 cổng chặn (`vat_lieu_kho.py:184`, `qr_token.py:57`, `vat_lieu_kho_service.py:163` và `:232`), 3 bảng tra (`HANG_NHAN`, `_REPOS`, `danh_muc_tham_chieu:277`), 1 chỗ FE chia quyền **nhị phân** (`KhoTonKhoPage.tsx:1084`) — thêm giá trị thứ ba là **im lặng ăn nhầm ô quyền**, cộng `stock_lots` · `stock_vouchers` · `stock_requests` · `purchase` đều mang cột này. Toàn code bên kho. |
| Bảng mới | Bảng mới **bắt buộc** kéo theo `hang_loai` thứ ba — kho không trỏ được vào bảng nó không biết. Hai thứ này dính nhau, không tách được. |

---

## 3. Quyết định kiến trúc — **menu riêng · bảng chung**

Chủ dự án chọn *"một menu riêng luôn ở chỗ Cấu hình danh mục"*. Được — nhưng chỗ **lưu** vẫn là
`vat_tu_in_an`, vì §2 dòng cuối.

```
MENU (Cấu hình danh mục)      Ô QUYỀN            BẢNG THẬT        KHO NHÌN THẤY
──────────────────────────    ───────────        ──────────       ─────────────
  Giấy                        dm_giay      ───►  giay_nguyen ───► hang_loai="giay"

  Vật tư khác                 dm_vat_tu    ──┐
  Thành phẩm  ★MỚI            dm_thanh_pham ─┴►  vat_tu_in_an ──► hang_loai="vat_tu"
                                                      │
                                     customer_id IS NULL  → hiện ở "Vật tư khác"   (đến 19/08/2026)
                                     customer_id NOT NULL → hiện ở "Thành phẩm"    (đến 19/08/2026)
```

> **Đổi 21/08/2026 (mg 0228):** hai dòng công tắc cuối ở trên **không còn đúng**. Công tắc thật
> hiện tại là cột cờ riêng: `la_thanh_pham = false → "Vật tư khác"`,
> `la_thanh_pham = true → "Thành phẩm"`. `customer_id` không còn tham gia phân loại — xem §6.

**MỘT dòng giữ toàn bộ quyết định này đứng vững:** `_mat_hang_row()` trả `hang_loai="vat_tu"` cho
thành phẩm, chỉ đổi **nhãn nhóm** thành *"Thành phẩm"*. Kho không biết có menu thứ ba, và **không
phải sửa một dòng nào** trong luồng nhập kho · lập phiếu · trừ tồn.

Nói cách khác: `kind` (danh mục nào — chuyện của màn khai báo) và `hang_loai` (bảng nào — chuyện
của sổ kho) là **hai không gian tên khác nhau**. Menu thứ ba sống ở không gian thứ nhất và **không
tràn** sang không gian thứ hai.

---

## 4. Luồng

```
BÁN HÀNG
  Đơn DH-2026-041 (draft)
    ├─ dòng #11  Hộp thuốc 10 vỉ — in 2 màu, cán bóng   12.000 hộp
    └─ dòng #12  Tờ HDSD gấp 3                          12.000 tờ
              │
        [ Chốt đơn ]  ── OrderService.confirm() ──┐
              │                                   │ TỰ KHAI (không ai bấm)
              ▼                                   ▼
       status = ordered              DANH MỤC ▸ THÀNH PHẨM ★MỚI
       (khoá cứng, không sửa dòng)     TP-DH-2026-041-11 · Hộp thuốc…
                                       TP-DH-2026-041-12 · Tờ HDSD gấp 3
                                                  │
SẢN XUẤT  ── in xong ─────────────────────────────┤
                                                  ▼
KHO       Nhập kho thành phẩm  (màn Tồn kho sẵn có, chọn ở ô tìm mặt hàng)
                                                  │  → stock_lots
                                                  │
GIAO HÀNG [ Tạo yêu cầu giao ] ◄──────────────────┘
              │   (chỉ tích dòng + số lượng — KHÔNG chọn mặt hàng)
              ▼
          Lên kế hoạch → [ Gửi yêu cầu xuất kho ]
              │            form điền sẵn từ yêu cầu, KHOÁ
              ▼
KHO       stock_requests XUẤT → lập phiếu → trừ tồn   (luồng cũ, y nguyên)
```

---

## 5. Luật

- **L1 — Chốt đơn là tự khai.** `OrderService.confirm()` khai mọi dòng của đơn. Không nút, không
  màn, không ai bấm. Neo ở `confirm()` chứ không ở lúc lập yêu cầu giao, vì kho phải **nhập kho
  thành phẩm được ngay khi sản xuất xong** — không phải chờ ai đó nghĩ đến việc lập yêu cầu giao.
- **L2 — Định danh là `(khách hàng, tên đã chuẩn hoá)`.** Mã `TP-<mã khách>-<nnn>`
  (`TP-KH001-001`), số thứ tự riêng theo từng khách.

  > **Sửa 19/08/2026, sau khi chủ dự án bắt lỗi.** Bản đầu lấy khoá `TP-<số đơn>-<id dòng>`:
  >
  > ```
  > Th08  Khách A · đơn 041 · dòng #11  "Hộp thuốc 10 vỉ"  → TP-…-041-11
  > Th09  Khách A · đơn 052 · dòng #77  "Hộp thuốc 10 vỉ"  → TP-…-052-77   ⚠️ dòng THỨ HAI
  > ```
  >
  > Nặng nhất **không phải** danh mục phình, mà là **TỒN KHO BỊ XÉ ĐÔI**: hàng dư tháng 8 nằm ở
  > dòng một, hàng in tháng 9 nằm ở dòng hai, và kho không trả lời được *"còn bao nhiêu Hộp thuốc
  > 10 vỉ"* — đúng câu duy nhất họ cần.

  **Phải có KHÁCH trong khoá:** hai khách đều có thể đặt *"Tờ hướng dẫn sử dụng — gấp 3"* mà là
  hai file in khác hẳn. Gộp lại là giao tờ của khách A cho khách B.

  **So tên đã CHUẨN HOÁ**, không so nguyên văn: bỏ hoa/thường · gộp khoảng trắng · mọi kiểu gạch
  ngang (`—` `–` `-`) về một · gọt dấu câu hai đầu. Người lập đơn tháng sau gõ lại bằng tay, lệch
  một dấu là bản so-nguyên-văn đẻ thêm dòng — đúng cái lỗi đang sửa. **Không bỏ dấu tiếng Việt**:
  *"Bìa"* và *"Bia"* là hai thứ khác nhau.

  > **Đổi tiếp 21/08/2026 (mg 0228) — "phải có KHÁCH trong khoá" ở trên KHÔNG CÒN đúng.** Khoá gộp
  > trùng bỏ hẳn khách ra, chỉ còn **tên đã chuẩn hoá**. Hai khách đặt cùng tên hàng giờ DÙNG CHUNG
  > một dòng danh mục — ngược hẳn lý do "phải có khách" nêu trên. Mã cũng đổi từ `TP-<mã khách>-
  > <nnn>` sang **`TP-00001…`** (đếm chung toàn danh mục). Lý do đổi: thành phẩm là **tên hàng**,
  > không phải hồ sơ riêng của một khách — xem callout đầu file.
- **L3 — Tên là nguyên văn mô tả dòng đơn** (cắt 150 ký tự theo `vat_tu_in_an.ten`). Không rút
  gọn, không thêm chữ. Kho tìm bằng đúng cái tên khách đặt.
- **L4 — Hai danh mục rời hẳn nhau.** Vật tư khác **không** hiện thành phẩm; Thành phẩm **không**
  hiện mực/kẽm/hoá chất. Không dòng nào hiện ở hai chỗ.
- **L5 — Khai tay ĐƯỢC, nhưng bắt chọn khách hàng.**

  > **Nới 19/08/2026.** Bản đầu cấm khai tay, viện luật siết 08/08/2026 của kho — **tôi đọc sai**:
  > luật đó bỏ ô tên **tự do trên phiếu xuất** (`stock_request_lines.ten_tu_do`), nó không cấm khai
  > danh mục. Mọi danh mục khác đều khai tay được; cấm ở đây là không cho Bán hàng khai trước một
  > món khách sắp đặt.

  Bắt buộc `customer_id` — nó vừa là chủ, vừa là công tắc chia hai màn, vừa là phạm vi gộp trùng.
  Để trống thì dòng vừa khai **rơi sang màn Vật tư khác và biến mất khỏi màn vừa tạo nó**, không
  lỗi gì cả.

  > **Đổi tiếp 21/08/2026 (mg 0228) — hết bắt buộc.** Công tắc chia màn tách riêng ra thành cột
  > `la_thanh_pham`; `customer_id` không còn giữ vai trò công tắc nữa nên **không còn bắt buộc**.
  > Khai tay để trống khách vẫn hiện đúng ở màn Thành phẩm — không còn "rơi sang Vật tư khác" như
  > mô tả ở trên.

  **Tên SỬA ĐƯỢC** (gõ sai chính tả phải sửa được — và vì tên là khoá gộp, sửa tên chính là cách
  gộp hai dòng lỡ đẻ trùng). **Mã thì KHÔNG**: nó đã nằm trong lô tồn và phiếu đã ghi sổ.
- **L6 — Kho vẫn tìm thấy.** Ô tìm mặt hàng (`/api/vat-lieu-kho/mat-hang`) quét thêm thành phẩm,
  nhóm hiện *"Thành phẩm"*, nhưng `hang_loai` trả về là `vat_tu` (§3).
- **L7 — Huỷ đơn KHÔNG xoá thành phẩm.** Lúc huỷ có thể đã nhập kho rồi; xoá dòng danh mục là làm
  **mồ côi lô tồn**. Chỉ `active=false`.

---

## 6. Dữ liệu — **0 bảng mới, 2 cột** *(đã lỗi thời — xem callout đầu file)*

```
vat_tu_in_an   + customer_id    INTEGER NULL   ← CHỦ + công tắc + phạm vi gộp trùng   (mg 0204)
               + order_id       INTEGER NULL   ← đơn ĐẦU TIÊN đặt món này (chỉ để tra) (mg 0203)
               + order_line_id  INTEGER NULL   ← dòng đơn đầu tiên       (chỉ để tra) (mg 0203)
               index (customer_id), index (order_line_id)
```

`customer_id` làm **ba việc cùng lúc, cố ý**: **chủ** (file in là của riêng khách đó) · **công
tắc** chia hai màn (§3) · **phạm vi gộp trùng** (L2). Thêm một cột `la_thanh_pham` nữa là hai nguồn
sự thật cho cùng một câu hỏi, lệch nhau lúc nào không biết.

Công tắc này đúng **nghĩa**, không phải mẹo: mực/kẽm/hoá chất mua từ **nhà cung cấp**, không bao
giờ thuộc về khách; thành phẩm thì **luôn** thuộc một khách.

`order_id` / `order_line_id` giữ lại làm **nguồn gốc** (lần đầu đặt ở đơn nào), **không** cập nhật
ở những lần đặt sau, và **không** còn là khoá định danh.

> **Đổi tiếp 21/08/2026 (mg 0228) — đúng điều đoạn trên cảnh báo đã xảy ra.** Thêm cột
> **`la_thanh_pham BOOLEAN NOT NULL DEFAULT false`** làm công tắc riêng, tách hẳn khỏi
> `customer_id`. Sơ đồ dữ liệu hiện tại:
> ```
> vat_tu_in_an   + la_thanh_pham   BOOLEAN NOT NULL DEFAULT false  ← CÔNG TẮC DUY NHẤT (mg 0228)
>                  customer_id     INTEGER NULL   ← chỉ còn là VẾT NGUỒN GỐC (khách đầu tiên đặt),
>                                                    không bắt buộc, không phải khoá gộp trùng
>                  order_id / order_line_id        ← không đổi, vẫn chỉ để tra nguồn gốc
> ```
> `_VatTuRepo.extra_conds` lọc `la_thanh_pham.is_(False)`; `_ThanhPhamRepo.extra_conds` lọc
> `la_thanh_pham.is_(True)` và `_ThanhPhamRepo._sau_gan` tự đóng dấu `la_thanh_pham=True` khi tạo
> qua màn Thành phẩm. Cross-check hai màn không đá nhau nằm ở
> `MotDanhMucVatLieu._dung_man` (`backend/app/services/vat_lieu_kho_service.py:425-451`), so trực
> tiếp cột `la_thanh_pham` — không còn so `customer_id`.

Không FK cứng sang `orders` / `order_lines`: cùng khuôn soft-ref mà `stock_requests.purchase_
delivery_id` và `delivery_trip_id` đã dùng — danh mục sống lâu hơn đơn (L7).

---

## 7. Quyền — `dm_thanh_pham`

Thêm **1 dòng** vào `catalog_registry.DANH_MUC` ⇒ menu · ma trận quyền · nhật ký · seed module
**tự lan** (đó đúng là lý do file `catalog_registry.py` tồn tại — xem chú thích đầu file đó).

Migration **chép quyền từ `dm_vat_tu`** sang `dm_thanh_pham` để không vai nào mất quyền đang có
sau khi deploy. `module_key` là **dữ liệu sống** — đổi chuỗi này về sau phải có migration `UPDATE`.

---

## 8. Màn hình — `Cấu hình danh mục ▸ Thành phẩm`

Dùng nền `RebuildCatalogPage` sẵn có (config-driven), chỉ thêm **1 object config** + 1 dòng menu.

Bảng dưới đây là form **19/08/2026** — ĐÃ LỖI THỜI, xem callout ngay sau bảng.

| Cột | Ví dụ |
|---|---|
| Mã | `TP-KH001-001` |
| Tên | Hộp thuốc 10 vỉ — in 2 màu, cán bóng *(sửa được)* |
| **Khách hàng** | Dược phẩm Sao Mai *(bắt buộc)* |
| ĐVT | hộp *(sửa được)* |
| Ghi chú | *(sửa được)* |

> **Đổi 21/08/2026 — cột "Khách hàng" đã bị GỠ khỏi form.** Form hiện tại chỉ còn 4 ô: **Mã**
> (sinh tự động dạng `TP-00001`, khoá khi sửa) · **Tên** (sửa được, là khoá gộp trùng) · **ĐVT**
> (`don_vi_gia`, sửa được) · **Ghi chú** (sửa được). Không còn ô chọn khách hàng trên màn khai báo.

Cột **Khách hàng** không được thiếu: *"của ai"* chính là thứ phân biệt hai thành phẩm cùng tên.

Có nút **Thêm** (L5, nới 19/08/2026), ô Khách hàng đứng đầu và bắt buộc. **Không** nút Xoá — xoá
thành phẩm là làm mồ côi lô tồn (L7); ngừng dùng thì tắt `active`, đảo lại được.

---

## 9. Dữ liệu cũ — **xoá, không backfill**

6 dòng `TP-*` seed theo thiết kế cũ (`TP-HOP-BANH`, `TP-TEM-DAN`, `TP-SACH-T5`, `TP-BIA-LOT`,
`TP-HOP-THUOC`, `TP-TO-HDSD`) + 6 lô tồn của chúng → xoá bằng script rời, **không** nhét vào
migration (migration chạy cả trên prod, mà prod chưa bao giờ có mấy dòng này).

Đơn đã chốt từ trước **không** backfill. Đơn cũ nào cần giao thì **lưới an toàn** ở
`DeliveryService._mat_hang_cua_dong_don` khai lúc lập yêu cầu — cùng một hàm dùng chung với
`confirm()`, nên mã sinh ra giống hệt, không lệch.

---

## 10. Chỗ dễ sai (viết ra để lần sau khỏi cắn)

1. **`_mat_hang_row` trả `hang_loai=loai`.** Để nguyên là đẻ ra `hang_loai="thanh_pham"` mà
   `stock_lots` không nhận ⇒ **phải map về `"vat_tu"`**. Đây là mắt xích số một của §3.
2. **`_VatTuRepo` quên lọc** ⇒ thành phẩm hiện ở **cả hai** màn (vi phạm L4).
3. **Vòng `for loai in ("giay", "vat_tu")`** ở `vat_lieu_kho_service.py:232` quên thêm
   `"thanh_pham"` ⇒ kho **không tìm thấy thành phẩm để nhập kho**, mà **không có lỗi nào báo** —
   ô tìm chỉ trả về rỗng.
4. **Thêm cột phải cập nhật `docs/DB_SCHEMA.md` cùng lúc**, không thì `init` FAIL (guard test).
5. **`create_all` không ALTER.** Hai cột mới phải vào `db_migrations.py` mới tới được DB dev/prod.
6. **`tests/test_catalog_registry.py` là ẢNH CHỤP CỐ Ý GHIM** bảng registry để bắt lỗi *mất* khoá.
   Thêm màn thứ 11 làm đỏ 4 test ở đó — phải thêm ĐÚNG một dòng vào từng bảng kèm ghi chú, và đổi
   con số `== 10` thành `== 11`. **Đừng nới lỏng phép so sánh cho nó xanh**, làm thế là giết đúng
   cái tác dụng của file đó.
7. **`CatalogRepo.update` ghi cột `ma` riêng**, không đi qua `fields` — chặn tên/mã bằng `fields`
   là hụt, phải gỡ `ma` khỏi payload trong `_ThanhPhamRepo.update`.
8. **Router danh mục trả `422`** cho `VatLieuKhoValidationError`, không phải `400`. Test viết theo
   `400` thì đỏ, nhưng chặn vẫn đang ăn — đọc kỹ trước khi sửa code.
9. **ĐỪNG chặn tra-chéo trong `_VatTuRepo.get()`.** Đã thử và VỠ: kho tra mặt hàng
   `hang_loai="vat_tu"` đi qua đúng repo đó, mà thành phẩm với kho **là** `"vat_tu"` — 14 test đỏ
   với câu *"Không tìm thấy mặt hàng."* ngay ở bước lập yêu cầu xuất kho. Chốt chặn phải nằm ở
   `MotDanhMucVatLieu` — lớp **chỉ màn danh mục** đi qua. `extra_conds` thì an toàn vì nó chỉ vào
   `list()`, mà kho không liệt kê theo màn.

   > Đây là **mặt sau của §10.1**: chỗ kia sai vì để `thanh_pham` tràn sang không gian của kho;
   > chỗ này sai vì lấy luật của màn áp lên đường đi của kho. Cùng một ranh giới, hai chiều.

---

10. **CHỈ MỘT cột trả lời câu "có phải thành phẩm không" — `customer_id`.** Vỡ thật 20/08/2026:
    `MotDanhMucVatLieu._dung_man` phân biệt bằng `order_line_id` trong khi hai repo lọc bằng
    `customer_id`. Hai nơi hỏi cùng một câu bằng hai cột khác nhau thì sớm muộn lệch, và nó lệch
    ở **cả hai chiều**:

    | Dòng | `customer_id` | `order_line_id` | Hậu quả |
    |---|---|---|---|
    | Thành phẩm **khai tay** | có | không | hiện ở màn Thành phẩm, bấm vào ăn *"Không tìm thấy mặt hàng."* ⇒ khai xong không sửa được |
    | Dòng đời cũ | không | có | hiện ở màn Vật tư khác, bấm vào cũng lỗi |

    Test cũ chỉ kiểm lúc **TẠO** thành phẩm khai tay, không kiểm **mở ra sửa** — nên bỏ lọt. Thêm
    một ô CRUD thì phải kiểm đủ tạo · **mở** · sửa, không chỉ tạo.

---

## 11. Gợi ý tên ở phiếu tính giá — mắt xích khép vòng

> **Cập nhật 30/08/2026:** đã GỠ dropdown gợi ý (`ThanhPhamGoiY`) khỏi ô "Tên sản phẩm" — chủ dự
> án thấy thừa/rối sau khi có ô "Sản phẩm tái bản" riêng (docs/spec-san-pham-tai-ban.md) làm việc
> nạp cấu hình mạnh hơn nhiều. Ô "Tên sản phẩm" giờ là input text thường. Cơ chế dedup-theo-tên ở
> `order_service.py:428` KHÔNG đổi — vẫn so khớp chuỗi thuần, chỉ mất phần UI gợi ý gõ đúng tên
> cũ; gõ trùng tên (kể cả lệch chữ hoa/dấu, vì có chuẩn hoá) vẫn dùng lại đúng dòng danh mục cũ.

Dedup theo tên đã chuẩn hoá bắt được hầu hết ca đặt lại, nhưng vẫn là **suy đoán từ chữ**: khách
đổi cách mô tả là ra dòng mới.

Chủ dự án chỉ ra chỗ đúng để chặn (19/08/2026): **ô "Tên sản phẩm" ở phiếu tính giá** — chỗ cái
tên được gõ ra LẦN ĐẦU.

> *"Chỗ lập phiếu tính giá, nó có phần thêm sản phẩm này rồi nè, nếu mà nó có ở thành phẩm rồi thì
> cho họ dùng lại… nếu không có thì thôi, lúc chốt thì tạo mới."*

Đo lại thì thấy tên đi thẳng tới đích **không biến dạng**:

```
Phiếu tính giá        Báo giá                 Đơn hàng bán           Danh mục
"Tên sản phẩm"  ──►  quote_items          ──► order_lines       ──► khoá gộp trùng
  c.ten               .product_name            .description          (khách, tên chuẩn hoá)
                                          order_service.py:428
```

⇒ **Chỉ cần gợi ý ĐÚNG TÊN là đủ.** Không cần cột nối `order_lines.thanh_pham_id` nào cả — bản
trước tôi định thêm cột đó, thừa. Quyền cũng có sẵn: `tinh_gia_thanh.read` đã nằm trong cổng đọc
danh mục (`_DOC_CHUNG`).

**Component `ThanhPhamGoiY`** — khác `MaterialCombobox` ở đúng một điểm quyết định: ô kia **ép
phải chọn** (luật kho 08/08/2026), ô này **gõ tự do là chính, gợi ý là phụ**. Sản phẩm lần đầu làm
thì chưa có gì để chọn; ép chọn ở đây là lặp lại đúng cái sai đã phải gỡ ở màn Giao hàng.

**KHÔNG lọc theo khách.** Phiếu tính giá chưa biết khách (`phieu_tinh_gia` không có cột khách —
khách chỉ gắn ở bước báo giá), và theo chủ dự án thì *"nó chỉ là tên thành phẩm thôi… có thì mình
dùng lại tên đó"*. Danh sách vẫn hiện **tên khách từng đặt** bên cạnh — không để lọc, mà để người
tính giá nhận ra *"món này mình làm rồi"*.

Hệ quả cần biết: chọn một tên của khách KHÁC thì lúc chốt vẫn dedup trong phạm vi khách **thật**
của đơn ⇒ sinh dòng mới cho khách đó, cùng tên. Đó là **đúng**: cùng một mô tả cho hai khách là
hai file in khác nhau, và tồn kho phải tách (§5 L2).

---

## 12. Câu còn hở

Đơn **sửa mô tả dòng sau khi chốt** thì tên trong danh mục có đổi theo không?

Hiện `OrderService.update()` chặn đơn `ordered` (chỉ cho sửa `draft`) nên **không xảy ra** — cố ý
không viết code đồng bộ, vì code đồng bộ cho một luồng không tồn tại là code không ai kiểm được.
Nếu sau này mở cho sửa đơn đã chốt thì **phải bàn lại chỗ này**.
