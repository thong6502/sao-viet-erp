# PRODUCT_SENSE.md

Durable product judgment for the SVN ERP that agents can't infer from code alone. The
Planner and Generator draw on this when writing specs and building screens.

## North star

**Build an ERP a real print factory actually runs on — excellent and easy to use.**
Not a demo. A screen is worth shipping only when a real SVN employee could do their actual
job on it, end to end, without hitting a gap.

## Who it's for

- **Kinh doanh** (sales): tra khách, tính giá, báo giá, chốt đơn, theo dõi công nợ.
- **Xưởng** (production): nhận lệnh, ghi sản lượng/hao hụt theo tổ, KCS.
- **Kế toán**: công nợ, giá thành, thu/chi, kết xuất MISA.
- Người dùng làm việc **cả ngày, lặp lại nhiều lần** → tốc độ, ít click, ít gõ, thấy trạng thái ngay là tối quan trọng.

## Definition of "done" — 6 nguyên tắc sắc (thay cho "dùng được" mơ hồ)

A screen is done when ALL hold. These are judged by an independent evaluator (see EVALUATION.md).

1. **Chọn, đừng gõ.** Mọi tham chiếu (khách/SP/giá/chứng-từ-nguồn) là **picker tìm-kiếm trả
   về bản ghi thật** — 0 ô nhập ID/tên tự do. Chọn xong tự điền dữ liệu master.
2. **Luôn thấy ngữ cảnh liên quan.** Màn chi tiết hiện **dữ liệu sống từ module khác** +
   drill-through (Đơn→LSX/Báo giá/Giao/Công nợ; Tính giá→proof/Báo giá; Khách→lịch sử).
3. **Trường thật, kiểm thật.** Đủ trường theo nghiệp vụ thật (không cắt còn 3 ô); validation
   **server-side**; đúng luật VN (MST 10/13 số, thuế 0/5/8/10%/KCT, làm tròn đồng, đơn vị quy đổi).
4. **Thà trống trung thực còn hơn số giả.** Module đích chưa có → hiện "chờ phân hệ X" (seam).
   **Tuyệt đối không bịa số.**
5. **Đủ trạng thái + dễ dùng.** Rỗng/tải/lỗi đều xử lý; người dùng làm xong việc trong ít
   bước, liếc là thấy trạng thái/ngữ cảnh; điều hướng bàn phím được.
6. **Đầu ra có thương hiệu.** Chứng từ gửi ra (báo giá, đơn, phiếu giao, hóa đơn) xuất **PDF có
   letterhead SVN** (kéo từ Hồ sơ công ty; tiếng Việt là đủ).

## Product rules

- **Nhập một lần, chảy xuyên module** — master ghi 1 chỗ; chứng từ tham chiếu, không gõ lại.
- **Chốt = snapshot** — sửa master sau không làm đổi chứng từ đã chốt.
- **Trạng thái đa trục** (giao/hóa đơn/thu tiền/SX song song), lan truyền từ chứng từ con lên cha.
- Ambiguity = spec gap để nêu, **không phải cớ để đoán/lấp bừa**.
- Ưu tiên **độ tin cậy người dùng thấy được** hơn số lượng tính năng.

## No-Go patterns (10 dấu hiệu "demo đồ chơi" — dính 1 là RỚT)

1. Ô gõ ID/tên tự do cho tham chiếu (thay vì picker).
2. Màn thiếu panel dữ liệu liên quan / không truy vết được document flow.
3. Một trường "status" text đổi tự do (không máy trạng thái, không đa trục).
4. Tồn kho/số liệu chỉ là con số hiển thị, không sinh giá vốn/không ràng buộc.
5. Không BOM/định mức/bù hao ở chỗ nghiệp vụ đòi.
6. Bịa số ở chỗ đáng ra là seam "chờ phân hệ X".
7. Thiếu trường bắt buộc theo checklist thực thể; mọi trường optional.
8. Không audit trail / không phân quyền ở chỗ nghiệp vụ đòi.
9. PDF/chứng từ gửi ra trơ, không letterhead SVN.
10. Thiếu state (rỗng/tải/lỗi) hoặc nhập lại số liệu ở mỗi module.

> Chi tiết trường thật + luật VN + luồng chứng từ: bám kiến thức trong spec và
> [CROSS_MODULE_LINKS.md](./CROSS_MODULE_LINKS.md); mức UI/UX cần chạm: [UI_DESIGN.md](./UI_DESIGN.md)
> + `docs/design-assets/`. Cách chấm: [EVALUATION.md](./EVALUATION.md).
