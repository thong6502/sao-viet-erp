/** Thông tin pháp nhân — in trên chứng từ (mẫu Bộ Tài chính, báo giá gửi khách).
 *
 * Nguồn: biểu mẫu Phiếu chi/Phiếu thu công ty đang dùng (khảo sát 2026-07).
 * Các trường chưa có số liệu xác nhận (MST, điện thoại, email, website) để `null` —
 * KHÔNG bịa; nơi dùng tự bỏ qua hoặc in "—".
 */
export const COMPANY = {
  name: "CÔNG TY CỔ PHẦN IN SAO VIỆT NHẬT",
  address:
    "1/473, Khu Phố Hòa Lân 2, Phường Thuận Giao, Thành phố Hồ Chí Minh, Việt Nam.",
  taxCode: null as string | null,
  phone: null as string | null,
  email: null as string | null,
  website: null as string | null,
} as const;
