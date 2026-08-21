# Thiết kế DAG kéo ngang

## Mục tiêu

Sơ đồ routing giữ zoom do người dùng điều khiển và cuộn được cả ngang lẫn dọc để xem node ngoài khung.
Canvas không để chiều cao cố định với phần trống lớn.

## Hành vi

- Giữ layout phân tầng hiện có và kích thước node 240px.
- Tính chiều rộng nội dung từ node ngoài cùng để sinh vùng cuộn ngang thật.
- Tính chiều cao nội dung từ node thấp nhất để sinh vùng cuộn dọc khi có nhiều nhánh.
- “Sắp xếp tự động” đưa về 100% và đầu tuyến; sau đó zoom không bị tự động ghi đè.
- Giữ zoom, pan thủ công và thuật toán sắp xếp hiện có.
- Chiều cao viewport dựa trên số node nhiều nhất trong một tầng, có min/max để không giật layout.

## Không thay đổi

- Không đổi thuật toán phụ thuộc, cách nối/xóa dây, kéo node hoặc dữ liệu routing.
- Không bẻ tuyến tuyến tính thành nhiều hàng.
