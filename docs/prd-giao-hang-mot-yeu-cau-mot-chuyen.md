# PRD — Giao hàng: MỘT yêu cầu = MỘT chuyến

> **Bản bổ sung, thay thế §7 · §9 và một phần §12 của `docs/prd-giao-hang.md`.**
> Chốt ngày 22/08/2026. Phần còn lại của PRD gốc giữ nguyên hiệu lực.

---

## 0. Chốt trong một câu

Chủ dự án: *"mỗi yêu cầu giao hàng là một chuyến giao cho nó dễ; nó giao thiếu hay đủ thì mình chỉ
ghi nhận thôi; muốn giao lại thì phải gửi yêu cầu mới cho dễ hiểu."*

Bỏ tầng "lần giao" như một thực thể đếm được. **Một yêu cầu giao chỉ sinh đúng một chuyến, và
chuyến đó chỉ có một kết cục.** Giao lại = yêu cầu mới.

---

## 1. Vì sao đổi — bằng số, không bằng cảm giác

Đếm trên DB ngày 22/08/2026:

| | |
|---|---|
| Yêu cầu giao | 3 |
| Chuyến giao | 3 |
| **Yêu cầu có quá 1 chuyến** | **0** |

Khả năng "nhiều chuyến một yêu cầu" đã dựng đủ (`lan_thu`, `hen_lai`, `chờ giao lại`, trạng thái
yêu cầu suy từ các chuyến) nhưng **chưa ai dùng một lần nào**. Nó bắt người dùng hiểu hai tầng
để đổi lấy một tình huống chưa xảy ra.

Chi phí đang gánh:

| Thứ | Số nơi tham chiếu (BE / FE) |
|---|---|
| `lan_thu` | 12 / 6 |
| `hen_lai` + `ngay_hen_lai` | 13 / 9 |
| `cho_giao_lai` | 2 / 4 |
| `trip_dang_chay` | 3 / — |

---

## 2. Mô hình mới

```
Đơn hàng bán
   └── Yêu cầu giao  (1)──(1)  Chuyến giao
                                  └── kết cục: thành công · giao thiếu · thất bại
```

**Yêu cầu giao** nay sở hữu trọn vòng đời. Không còn hàm suy trạng thái từ tập chuyến.

### 2.1 Trạng thái — MỘT tầng

| Trạng thái | Nghĩa |
|---|---|
| `cho_len_ke_hoach` | vừa tạo, chưa xếp người/giờ |
| `da_len_ke_hoach` | đã có nhân viên + giờ lấy/giờ giao |
| `dang_chuan_bi` | kho đã lập phiếu, đang soạn hàng |
| `da_lay_hang` | tài xế đã cầm hàng |
| `dang_giao` | đang trên đường |
| `thanh_cong` | khách nhận **đủ** |
| `giao_thieu` | khách nhận **một phần** — phần còn lại **về kho** |
| `that_bai` | khách **không nhận** — toàn bộ **về kho** |
| `dang_tra_hang` | xe đang chở hàng về |
| `da_tra_hang` | kho **đã nhập lại** hàng ⇒ **kết thúc** |
| `da_huy` | huỷ khi chưa lấy hàng |

**BỎ:** `hen_lai` · `ngay_hen_lai` · `lan_thu` · hướng xử lý `cho_giao_lai`.

> Vì sao bỏ `hen_lai`: nó là trạng thái "treo" — chuyến chưa xong mà cũng không kết thúc, hàng
> nằm trên xe không biết tới bao giờ. Nay khách hẹn lại = **thất bại lần này, trả hàng về, lập
> yêu cầu mới cho ngày hẹn**. Rõ hàng đang ở đâu tại mọi thời điểm.

### 2.2 Giao thiếu — ghi nhận rồi ĐÓNG

Giao 800/1.200 hộp:

1. Ghi kết quả `giao_thieu`, nhập số thực nhận từng dòng → cộng 800 vào "đã giao" của đơn;
2. Yêu cầu **đóng lại**, không mở chờ đợt sau;
3. 400 hộp còn lại **quay về kho** (xem §3);
4. Muốn giao nốt → **lập yêu cầu mới**. Không phải gõ lại: ô *"còn phải giao"* của đơn tự trừ
   phần đã giao, nên yêu cầu mới điền sẵn đúng 400.

---

## 3. Điều kiện bắt buộc — HÀNG VỀ KHO PHẢI VÀO SỔ

**Đây là phần quan trọng nhất của bản này. Làm mô hình 1:1 mà thiếu phần này là làm sai sổ kho.**

### 3.1 Lỗ hiện tại

`DeliveryService.kho_nhan_lai_hang()` hôm nay **chỉ đổi nhãn trạng thái sang `da_tra_hang`** —
không lập phiếu nhập kho nào. Hàng đã xuất cho chuyến hỏng thì **sổ kho vĩnh viễn coi là đã xuất**,
dù xe đã chở về và thủ kho đã cầm hàng.

Hôm nay lỗi này **chưa lộ**, vì đường `chờ giao lại` giữ hàng trên xe rồi giao tiếp bằng chuyến mới
— không xuất kho lần hai. Bỏ đường đó đi là lỗi lộ ngay:

```
Yêu cầu 1: xuất kho 1.200 hộp → giao hỏng → xe chở về   (sổ kho: đã xuất 1.200)
Yêu cầu 2: xuất kho 1.200 hộp lần nữa                    (sổ kho: đã xuất 2.400)
                                          thực tế hàng đi khỏi kho: 1.200
```

### 3.2 Phải làm

Khi thủ kho bấm **"Đã nhận lại hàng"**, hệ **lập phiếu NHẬP kho** cho đúng phần không tới tay
khách:

| Kết cục | Số nhập lại |
|---|---|
| `that_bai` | **toàn bộ** số đã xuất cho chuyến |
| `giao_thieu` | số đã xuất **trừ** phần khách thực nhận |
| `thanh_cong` | 0 — không có bước trả hàng |

Ràng buộc:

- Nhập lại vào **đúng kho đã xuất** — không cho chọn kho khác, vì đây là đảo lại một phiếu cụ thể.
- Phiếu nhập **trỏ ngược** về chuyến (`delivery_trip_id`) để đối chiếu được.
- Chuyến chỉ sang `da_tra_hang` **sau khi** phiếu nhập lập xong. Đổi nhãn trước rồi lập phiếu sau
  là mở cửa cho trạng thái nói một đằng sổ kho một nẻo.
- Lập hai lần ⇒ **chặn**, nêu mã phiếu đã có (cùng khuôn `gui_yeu_cau_xuat_kho` đang chặn).

---

## 4. Cái gì KHÔNG đổi

- Yêu cầu giao vẫn **suy dòng hàng từ đơn**, không gõ tay (luật 19/08/2026).
- Vẫn phải **gửi yêu cầu xuất kho** và kho lập phiếu như mọi phiếu vật tư khác.
- **Kho nào xuất do thủ kho chọn** (chốt 21/08/2026) — yêu cầu không ghi kho.
- Chặn trùng lịch tài xế, `km >= 0`, lịch sử đổi trạng thái, phân quyền, real-time: nguyên vẹn.
- Một **đơn** vẫn tạo được **nhiều yêu cầu** giao. Chỉ quan hệ *yêu cầu → chuyến* mới thành 1:1.

---

## 5. Điều kiện nghiệm thu — thay cho §12 của PRD gốc

Ba dòng cũ bị thay:

| Cũ | Mới |
|---|---|
| #3 "một yêu cầu chỉ có một lần giao đang hoạt động" | **#3′** Một yêu cầu chỉ tạo được **đúng một** chuyến. Gọi tạo lần hai ⇒ chặn. |
| #9 "tạo lần giao lại không nhân đôi số lượng" | **#9′** Giao thiếu/thất bại xong, **lập yêu cầu mới** cho phần còn lại ⇒ tổng đã giao **không** nhân đôi. |
| #14 "lần giao lại cũng phải gửi đề nghị" | **#14′** Yêu cầu mới đi lại **trọn quy trình** như yêu cầu đầu — không có lối tắt. |

Thêm mới:

19. Chuyến `that_bai` → thủ kho *Đã nhận lại hàng* ⇒ sinh **phiếu nhập kho** đúng **toàn bộ** số
    đã xuất, vào **đúng kho đã xuất**.
20. Chuyến `giao_thieu` (giao 800/1.200) → nhận lại ⇒ phiếu nhập đúng **400**, không phải 1.200.
21. Chưa lập được phiếu nhập ⇒ chuyến **không** sang `da_tra_hang`.
22. Bấm *Đã nhận lại hàng* lần hai ⇒ **chặn**, nêu mã phiếu nhập đã có.
23. Sau khi trả hàng về, ô *"còn phải giao"* của đơn **trở lại đúng số cũ** ⇒ lập được yêu cầu mới
    cho trọn phần đó.
24. Trạng thái `hen_lai` **không còn tồn tại**: gọi API ghi kết quả với `hen_lai` ⇒ **422**.

---

## 6. Dữ liệu & migration

- **Không thêm bảng.** `delivery_trips` giữ nguyên, thêm ràng buộc *một chuyến / một yêu cầu*.
- `lan_thu` — **giữ cột, ngưng dùng** (luôn `1`). Không drop: 3 chuyến đang có mang giá trị thật,
  và drop cột là việc không đảo được. Ngưng dùng thì đảo lại được nếu chủ đổi ý.
- `ngay_hen_lai` — **giữ cột, ngưng ghi**. Dòng cũ có số thì vẫn tra được.
- Migration mới: chỉ số **UNIQUE trên `delivery_trips.request_id`** để CSDL tự chặn chuyến thứ hai.
  Dữ liệu hiện tại đã thoả (0 yêu cầu có quá 1 chuyến) nên không cần dọn trước.
- Phiếu nhập trả hàng dùng lại `stock_requests` / phiếu kho sẵn có + cột soft-ref
  `delivery_trip_id` **đã có**. Không đẻ chứng từ mới.

---

## 7. Giao diện

- Màn Giao hàng: gộp hai thẻ *"Yêu cầu"* và *"Chuyến"* thành **một** dòng — hết cảnh mở yêu cầu
  rồi mở tiếp chuyến bên trong.
- Bỏ nút/ô liên quan `hẹn lại`, bỏ nhãn *"lần thứ N"*, bỏ lựa chọn *"chờ giao lại"* trong hộp thoại
  ghi kết quả (chỉ còn **trả về kho**).
- Ghi kết quả thất bại: câu chốt đổi thành *"Hàng sẽ được trả về kho. Muốn giao lại, lập yêu cầu
  mới."* — nói trước hệ quả, đừng để người dùng phát hiện sau.

---

## 8. Rủi ro & chỗ dễ làm sai

| Rủi ro | Chặn bằng |
|---|---|
| Đổi nhãn `da_tra_hang` trước khi lập phiếu nhập ⇒ sổ kho lệch âm thầm | nghiệm thu #21 |
| Nhập lại **toàn bộ** cho ca giao thiếu ⇒ thừa hàng trong sổ | nghiệm thu #20 |
| Nhập lại vào **kho khác** kho đã xuất ⇒ tồn hai kho cùng sai | ràng buộc §3.2 |
| Bấm nhận lại hai lần ⇒ nhập kho hai lần | nghiệm thu #22 |
| Gỡ `hen_lai` mà quên dòng dữ liệu cũ đang ở trạng thái đó | đếm trước khi gỡ; hiện **0 dòng** |

---

## 9. Việc phải làm, theo thứ tự

> **Trạng thái 22/08/2026 — ĐÃ LÀM XONG cả 5 bước.** `prd-giao-hang.md` (§7 · §9 · §12) và
> `DB_SCHEMA.md` đều đã trỏ sang bản này.
>
> Ghi lại hai chỗ làm khác dự tính, vì chúng đổi thiết kế:
>
> 1. **Chuyến `giao_thieu` KHÔNG đổi trạng thái sang `dang_tra_hang`.** Bản đầu đẩy nó sang đó cho
>    gọn và test `#08b` đỏ ngay: mọi phép cộng "đã giao" chỉ đếm chuyến ở `thanh_cong`/`giao_thieu`,
>    nên phần khách ĐÃ NHẬN biến mất khỏi sổ. Nay ca giao thiếu **giữ nguyên trạng thái**, kho nhận
>    lại hàng thẳng từ đó; dấu hiệu "đã trả hàng" là **phiếu nhập tồn tại**, không phải trạng thái.
> 2. Vì (1), cổng chặn "đã có phiếu nhập trả hàng" là **hàng rào thật** ở ngả giao thiếu (ngả này
>    không có cổng trạng thái nào chặn bấm lần hai).

## 9b. Thứ tự gốc

1. **Phiếu nhập trả hàng trước** — vá lỗ sổ kho đang có, độc lập với phần đổi mô hình. Làm xong
   là hệ đã đúng hơn hôm nay dù chưa đụng gì khác.
2. Chặn chuyến thứ hai (unique index + cổng ở service).
3. Gỡ `hen_lai` / `cho_giao_lai` / nhãn `lần thứ N` khỏi service + giao diện.
4. Gộp hai tầng trên màn Giao hàng.
5. Cập nhật `docs/prd-giao-hang.md` (§7 · §9 · §12 trỏ sang bản này) và `docs/DB_SCHEMA.md`.

Bước 1 **đảo được** và tự nó có giá trị; bước 2–4 mới là phần đổi mô hình.
