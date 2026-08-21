# Spec — Báo cáo kho (kế toán) + Loại phiếu + Khóa kỳ + Export MISA

> Trạng thái: CHỐT thiết kế 2026-08-10, đang build. Liên quan: [spec-kho-de-nghi.md](spec-kho-de-nghi.md), mẫu `Copy of Nhap_kho.xls` (33 cột) + `Copy of Xuat_kho.xls` (51 cột).

## 1. Mục tiêu
Màn **Báo cáo kho** trong phần Kho, CHỈ **kế toán kho** vào — tổng hợp mọi lần nhập/xuất theo dòng, **khóa kỳ (chốt sổ)** kiểu MISA, và **export Excel** đúng mẫu MISA để đẩy sang phần mềm kế toán.

## 2. Phạm vi & quyền
- Quyền mới: action **`close_book`** → cột `role_permissions.can_close_book` (Boolean, server_default `false`).
- Gate: xem màn + export + chốt sổ đều cần `can_close_book`. Bật cho **Kế toán kho (role_id 14)** + **Giám đốc/admin (role_id 1)**.
- KHÔNG tái dùng `kho.can_read` (thủ kho + quản lý kho cũng có).

## 3. Loại phiếu (nhập tay ở YÊU CẦU)
- Ô **Loại** = SỐ nhập tay tự do (không dropdown), đặt trên **form Yêu cầu** → lưu `stock_requests.loai_kho` (SmallInteger, nullable). Báo cáo chỉ ĐỌC (join phiếu → yêu cầu) + đưa vào export.
- Tooltip nhắc nghĩa theo chiều (chuẩn MISA):
  - **Xuất**: 0=bán hàng · 1=sản xuất · 2=chi nhánh khác · 3=khác.
  - **Nhập**: 0=thành phẩm SX · 1=hàng bán trả lại · 2=khác · 3=hàng nhận gia công.
- **Loại thực dùng qua kho này** (chỉ dựng trường cho case thật): **Xuất SX (1)**, **Nhập mua (2)**, **Nhập thành phẩm (0)**.

## 4. Trường phiếu theo loại (TỐI THIỂU)
| Loại | Phiếu thêm gì |
|---|---|
| Xuất sản xuất (1) | KHÔNG thêm — "bộ phận nhận" = bộ phận yêu cầu (đã có) |
| Nhập mua (2) | **NCC + Đơn mua (PMH)** — tự fill từ đơn mua khi bấm "Nhập kho" |
| Nhập thành phẩm (0) | KHÔNG thêm — NCC để trống (nguồn nội bộ = SX) |

- **KHÔNG** nhập TK Nợ/Có, hóa đơn, giá bán, vận chuyển, chi nhánh trên phiếu → export để **TRỐNG** các cột đó → kế toán tự điền trên MISA sau.

## 5. Màn Báo cáo (bảng tổng hợp)
Mỗi **dòng hàng** của mỗi phiếu = 1 row (giống MISA). Cột hiển thị:
| Cột | Nguồn |
|---|---|
| Ngày ghi sổ *(= ngày hạch toán)* | phiếu `ghi_so_luc` |
| Ngày chứng từ *(= ngày lập phiếu)* | phiếu `ngay` |
| Số chứng từ | mã phiếu (PNK/PXK) |
| Loại | `stock_requests.loai_kho` (join) |
| Mã hàng · Tên hàng · ĐVT | vật tư |
| Số lượng · Đơn giá · Thành tiền | dòng phiếu |

- Lọc: **khoảng ngày ghi sổ** (bấm cột — dùng `DateFilterHead`), **kho**, **chiều** (nhập/xuất). Chỉ tính phiếu **đã ghi sổ** (posted) cho sổ kế toán.
- Cột nào có data thì fill; không thì để trống.

## 6. Khóa kỳ (chốt sổ)
- Nút **Khóa kỳ** → dialog kiểu MISA: hiện **ngày khóa hiện thời**, chọn **ngày khóa mới** + **phạm vi**: *Toàn kho* hoặc *kho cụ thể*. Bỏ ô "khóa sổ thủ kho / thủ quỹ". [Thực hiện]/[Hủy].
- Bảng `kho_khoa_so`: `id, kho_id (nullable — NULL = toàn kho), ngay_khoa (Date), nguoi_khoa_id, khoa_luc (datetime)`. **Append-only**; "hiện thời" = bản ghi mới nhất theo (kho_id). **Lùi ngày** để mở khóa = ghi bản ghi mới ngày nhỏ hơn.
- **Enforcement**: khi sửa/hủy/ghi sổ 1 phiếu ở kho K → chặn nếu `max(ngày_khóa_toàn_kho, ngày_khóa_kho_K) >= ngày mốc phiếu`. Mốc = ngày ghi sổ nếu đã ghi, ngày chứng từ nếu chưa. Lỗi: "Kỳ đã khóa sổ đến dd/mm/yyyy — không sửa được."
- Chỉ `can_close_book`.

## 7. Export Excel
- Xuất **đúng mẫu MISA**: Nhập → 33 cột (`Copy of Nhap_kho.xls`); Xuất → 51 cột (`Copy of Xuat_kho.xls`). 1 dòng hàng = 1 hàng Excel.
- Fill các cột có data (ngày HT/CT, số CT, loại, mã/tên hàng, ĐVT, SL, đơn giá, thành tiền, kho, số lô, HSD, NCC/đối tượng nếu có…); **để trống** TK Nợ/Có, hóa đơn, vận chuyển, chi nhánh, cost-center…
- Tôn trọng bộ lọc đang xem (khoảng ngày/kho/chiều). Chỉ `can_close_book`.
- Lib: `openpyxl`.

## 8. Thay đổi schema (migration bắt buộc — db_migrations.py + DB_SCHEMA.md)
1. `stock_requests.loai_kho` — SmallInteger, nullable.
2. Bảng mới `kho_khoa_so` (xem §6).
3. `role_permissions.can_close_book` — Boolean, server_default `false`; migration UPDATE bật cho role 1 + 14 (module `kho`).

## 9. Endpoints (BE)
- `GET  /api/kho/bao-cao/dong` — list dòng (filter ngày ghi sổ / kho / chiều). Cần `can_close_book`.
- `GET  /api/kho/khoa-so` — trạng thái khóa hiện thời (toàn kho + từng kho).
- `POST /api/kho/khoa-so` — set khóa `{ kho_id?, ngay_khoa }`. Cần `can_close_book`.
- `GET  /api/kho/bao-cao/export.xlsx` — tải file theo filter + chiều. Cần `can_close_book`.
- Chèn check khóa vào voucher update/cancel/post.
- Wire `loai_kho` vào request create/update.

## 10. Frontend
- Ô **Loại** (number + tooltip) trên form Yêu cầu ([KhoDeNghiPage.tsx](../frontend/src/pages/KhoDeNghiPage.tsx)).
- **NCC + đơn mua** trên phiếu Nhập (fill từ đơn mua).
- Nav mới **"Báo cáo kho"** (gate `can_close_book`) → trang `KhoBaoCaoPage`: bảng + filter (ngày/kho/chiều) + nút **Khóa kỳ** (dialog) + nút **Xuất Excel**.
- `client.ts`: types (`loai_kho`, báo cáo row, khóa-so, cap `can_close_book`) + api methods + tải blob xlsx.

## 11. Ngoài phạm vi (chưa làm)
Xuất bán hàng / xuất chi nhánh / nhập bán trả lại / nhập gia công; nhập TK Nợ-Có ở phiếu; ánh xạ TK tự động; giá bán, vận chuyển, hóa đơn trên phiếu. (Để trống khi export, chỉnh sau nếu cần.)
