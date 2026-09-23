# Plan sửa UI ngăn kéo "Đơn mua hàng mới"

Ảnh chụp cho thấy hàng dòng hàng nhân đôi nhãn: hàng tiêu đề xám (`Vật tư* | Nhà cung cấp* |
ĐVT* | …`) vẫn còn, nhưng trong hàng dữ liệu lại xen thêm một loạt chữ "Vật tư *", "Nhà cung
cấp *", "ĐVT *", "Số lượng *", "Tiền giảm", "VAT (%)", "Ghi chú dòng" đứng trước từng ô. 22 con
trong lưới 11 cột nên hàng dữ liệu gãy làm hai dòng và lệch hẳn khỏi tiêu đề, kèm thanh cuộn
ngang ngay trong ngăn kéo.

## 1. Nguyên nhân gốc — `responsive.css` vỡ cú pháp, chết 4.700 dòng

Nhãn xen giữa chính là `.purchase__line-lb` (`PurchaseFormDrawer.tsx:31`), thứ CỐ Ý chỉ bật ở
điện thoại. Nó được tắt bằng một luật **ngoài mọi media query** ở `styles/responsive.css:3195`:

```css
.purchase__line-lb { display: none; ... }
```

Luật đó đang **không chạy trên màn rộng**, vì file bị lẹm một khối:

- `responsive.css:553` mở `@media screen and (max-width: 768px) {` cho §22.
- Danh sách selector của §22 chạy tới `:623` rồi **kết thúc bằng dấu phẩy**, KHÔNG có
  `{ font-size: 12px !important; }` và KHÔNG có `}` đóng media.
- Trình duyệt nuốt luôn `@media` kế tiếp (`:631`) vào phần selector dở dang ⇒ **toàn bộ từ dòng
  553 đến hết file (5.331 dòng) nằm trong một khối `@media screen and (max-width: 768px)` duy
  nhất**, tự đóng ở EOF.

Đếm ngoặc (bỏ chú thích) trên `responsive.css`: `depth = 1` ở cuối file; lần cuối về 0 là dòng
541. Quét cả 60+ file CSS còn lại: chỉ một mình file này lệch.

Lịch sử: hỏng ở commit `7917b077` (18/09/2026). Diff cho thấy khi gỡ cụm "Xếp lịch 2"
(`.xl2-iconbtn`, `.xl2-seg__btn`) ở cuối danh sách §22, người sửa gỡ luôn cả thân khai báo và
dấu `}` đóng media:

```diff
-  /* Xếp lịch 2: nút chọn lát cắt và nút "Vừa khít" — 11,5px */
-  .shell__content .xl2-iconbtn,
-  .shell__content .xl2-seg__btn {
-    font-size: 12px !important;
-  }
-}
```

Vite không báo gì — CSS hỏng cú pháp vẫn build sạch, nên nó đi thẳng ra bản chạy.

### Hệ quả đo được

| Phạm vi | Tình trạng |
|---|---|
| Màn rộng | Chỉ đúng một chỗ hỏng: `.purchase__line-lb` là luật top-level DUY NHẤT sau dòng 624, nên nhãn điện thoại đổ ra desktop — đúng cái ảnh chụp. Hai chế độ Tạo và Sửa đều dính. |
| §22 (sàn cỡ chữ đợt 2, 51 lớp) + §23 (nút mở menu / chuông / ngăn kéo 44px) | **Chết hẳn** — cả hai bị nuốt vào cái selector hỏng. |
| 81 khối `@media …768px` sau dòng 624 | Còn sống (media lồng media cùng điều kiện). |
| 5 khối `max-width: 1024px`, 4 khối `max-width: 900px` | Bị ép về ≤768px ⇒ **mất dải 769–1024px** (máy tính bảng): dòng 922, 947, 1049, 1160, 1203, 1318, 2950, 4766, 5088. |
| 2 khối `hover: none` | Chỉ còn chạy khi máy cảm ứng hẹp ≤768px; tablet cảm ứng rộng mất phần này. |

## 2. Đợt 1 — vá cú pháp (1 chỗ, thắng ngay cái ảnh chụp)

`styles/responsive.css:623` — bỏ dấu phẩy cuối, trả lại thân khai báo và `}`:

```css
  .shell__content .khvt-header__sync {
    font-size: 12px !important;
  }
}
```

Xong là §22/§23 sống lại, các media 900/1024/hover trở về đúng dải, và `.purchase__line-lb` trở
lại `display: none` trên desktop — hàng dòng hàng về đúng 11 con/11 cột, gióng khít tiêu đề.

## 3. Đợt 2 — guard chặn tái phát

Thêm test vitest (`frontend/src/styles/cssCanBang.test.ts`): đọc mọi `**/*.css` trong
`frontend/src`, bỏ phần trong `/* */`, đếm `{`/`}`, khẳng định về 0 và không bao giờ âm. In ra
tên file + dòng lệch khi đỏ.

Lý do phải có: lỗi này im lặng tuyệt đối — không lỗi build, không cảnh báo, không test nào bắt;
nó sống 2 ngày và chỉ lộ ra vì nhìn bằng mắt. Một test 20 dòng chặn đúng khuôn lỗi đó.

## 4. Đợt 3 — cuộn ngang trong ngăn kéo (lỗi thiết kế thật, không phải hệ quả đợt 1)

Kể cả khi vá xong cú pháp, ngăn kéo này **luôn** phải kéo ngang:

- Ngăn kéo: `purchase.css:783` → `width: min(85vw, 900px)` ⇒ tối đa 900px.
- Lưới dòng hàng: `purchase.css:1848` chế độ TẠO `min-width: 1280px` (11 cột),
  `purchase.css:1836` chế độ SỬA `min-width: 1080px` (10 cột).

900 < 1080 < 1280 ⇒ Đơn giá, VAT, Thành tiền nằm ngoài tầm nhìn ở **mọi** cỡ màn. Mà đây là
biểu mẫu sinh đơn mua: người dùng gõ đơn giá rồi phải kéo ngang mới thấy thành tiền vừa gõ ra
bao nhiêu.

Hướng chữa (giữ dạng bảng, bỏ bớt cột chỉ-đọc chứ không bóp cột):

1. **Gộp ĐVT + Số lượng vào cột Vật tư** thành dòng phụ dưới tên: `Mực in offset Đen` /
   `5 kg`. Cả hai vốn là số liệu bộ phận đề nghị khai, Thu mua không sửa được — đang chiếm hai
   cột 76px + 92px chỉ để trưng bày.
2. **Gộp Tiền giảm xuống dưới ô Giảm (%)** thành chữ nhỏ (`−328.320 đ`). Nó là số dẫn xuất từ ô
   ngay trên.
3. Sàn bề ngang mới: `210 + 180 + 112 + 78 + 78 + 130 + 158 + 40` = 986px, cộng 7 khe × 8px và
   padding 20px ≈ **1.062px**. Nới ngăn kéo lên `min(92vw, 1100px)` ⇒ hết cuộn ngang từ laptop
   1366px trở lên.
4. Sửa kèm `NhanO` trong `PurchaseFormDrawer.tsx` cho khớp số cột mới (bản điện thoại một cột
   vẫn phải đủ nhãn), và `purchase.css:1963` (@≤1200px) theo số cột mới.

Giữ nguyên: không thêm/xoá dòng hàng, Vật tư/ĐVT/Số lượng vẫn chỉ-đọc, cột Thành tiền vẫn
`minmax(158px, …)` để tiền tỷ hiện trọn.

## 5. Xác minh

- Đợt 1 + 2: `npx vitest run src/styles/cssCanBang.test.ts` và `npx tsc --noEmit`.
- Đợt 3: thao tác lại đúng luồng bằng chuột trên dev-browser — Mua hàng → chọn yêu cầu → *Tạo
  đơn mua hàng* → gõ đơn giá, giảm %, VAT ở từng dòng → xem Thành tiền và "Sẽ tạo N đơn" → Lưu
  đơn → mở lại bản vừa lưu ở chế độ Sửa. Chụp lại ở 1920px, 1366px và 375px.
