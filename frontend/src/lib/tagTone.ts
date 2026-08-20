// Màu của một nhãn — suy TỪ CHÍNH CHUỖI nhãn, không cần lưu cột màu.
//
// Chép NGUYÊN thuật toán của nhãn khách hàng (KhachHangPage.tsx) để nhãn công đoạn ra ĐÚNG cùng
// một màu với cùng một chữ: nhãn nghĩa rõ (ưu tiên, tiềm năng…) có tông cố định; còn lại băm chuỗi
// → chọn trong bảng 8 tông. Yêu cầu "logic gán nhãn y như module khách hàng" bao gồm cả màu này.

export const TAG_TONES = [
  "indigo",
  "emerald",
  "violet",
  "cyan",
  "amber",
  "rose",
  "fuchsia",
  "teal",
] as const;

export const TAG_SEMANTIC_TONES: Record<string, string> = {
  "ưu tiên": "violet",
  "tiềm năng": "emerald",
  "tiềm năng cao": "emerald",
  "đối tác lâu năm": "indigo",
  "tái ký hđ": "teal",
  "trả đúng hạn": "emerald",
  "nhạy giá": "amber",
  "hay trễ hẹn": "rose",
  "khó tính": "rose",
  "ưa giao nhanh": "cyan",
  "cần chăm sóc": "amber",
  "chuộng mẫu đẹp": "fuchsia",
  "bao bì cao cấp": "indigo",
  // Nhãn hay gặp ở BƯỚC công đoạn (gia công ngoài xưởng) — cho tông cảnh báo ấm để đập vào mắt.
  "thuê ngoài": "amber",
  "gia công ngoài": "amber",
};

export function tagTone(label: string): string {
  const lower = label.trim().toLowerCase();
  if (TAG_SEMANTIC_TONES[lower]) return TAG_SEMANTIC_TONES[lower];
  let h = 0;
  for (const ch of label) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return TAG_TONES[h % TAG_TONES.length];
}
