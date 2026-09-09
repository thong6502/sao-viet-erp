"""Nghiệp vụ sổ tài sản cố định & công cụ dụng cụ.

Chia theo việc chứ không theo tầng: `khau_hao` là engine thuần (không DB, test bằng số học),
`service` giữ sổ + hai chứng từ biến động (điều chuyển · sửa chữa lớn) + đọc hao mòn từ lịch,
`bang_thang` dựng bảng khấu hao của một tháng (không kỳ, không chốt — từ 08/09/2026), `excel`
xuất bảng khấu hao. Ghi giảm và kiểm kê đã bỏ cùng ngày (chủ: "chỉ theo dõi khấu hao thôi").
"""
