// Nhãn trạng thái dùng chung của màn Giao hàng (tách từ pages/GiaoHangPage.tsx).
export const NHAN_TRANG_THAI_YC: Record<string, string> = {
  cho_len_ke_hoach: "Chờ lên kế hoạch",
  dang_thuc_hien: "Đang thực hiện",
  da_giao_du: "Đã giao đủ",
  da_huy: "Đã huỷ",
};

export const NHAN_TRANG_THAI_CHUYEN: Record<string, string> = {
  da_len_ke_hoach: "Đã lên kế hoạch",
  dang_chuan_bi: "Kho đang chuẩn bị",
  da_lay_hang: "Đã lấy hàng",
  dang_giao: "Đang giao",
  thanh_cong: "Giao thành công",
  giao_thieu: "Giao thiếu",
  hen_lai: "Khách hẹn lại",          // dòng CŨ trước 22/08/2026 — không còn khai mới
  that_bai: "Giao thất bại",
  dang_tra_hang: "Đang trả hàng",
  da_tra_hang: "Đã trả hàng",
  da_huy: "Đã huỷ",
};

export const NHAN_TRANG_THAI_NV: Record<string, string> = {
  ranh: "Rảnh",
  co_lich: "Có lịch",
  dang_giao: "Đang giao",
  dang_tra_hang: "Đang trả hàng",
  nghi: "Nghỉ",
};
