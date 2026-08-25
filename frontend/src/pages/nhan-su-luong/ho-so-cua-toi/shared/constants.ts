// Hằng dùng chung của màn "Hồ sơ của tôi" (tách từ pages/HoSoCuaToiPage.tsx).
import type { IconName } from "../../../../components/Icons";

export const STATUS_LABEL: Record<string, string> = {
  probation: "Thử việc", probation_ended: "Hết thử việc · chờ xác nhận",
  active: "Chính thức", on_leave: "Nghỉ dài hạn",
  suspended: "Đình chỉ", resigned: "Đã nghỉ",
};
export const STATUS_CLASS: Record<string, string> = {
  probation: "ns-badge--warn", active: "ns-badge--ok", on_leave: "ns-badge--info",
  suspended: "ns-badge--muted", resigned: "ns-badge--danger",
};
export const GENDER_LABEL: Record<string, string> = { male: "Nam", female: "Nữ", other: "Khác" };
export const DOC_KIND_LABEL: Record<string, string> = {
  hop_dong: "Hợp đồng", cccd: "CCCD", bang_cap: "Bằng cấp", khac: "Khác",
};
export const EVENT_LABEL: Record<string, string> = {
  hired: "Vào làm", confirmed: "Chuyển chính thức", transferred: "Điều chuyển",
  promoted: "Nâng bậc / đổi chức danh", leave_start: "Bắt đầu nghỉ dài hạn",
  leave_end: "Đi làm lại", suspended: "Đình chỉ", resigned: "Nghỉ việc", reinstated: "Tuyển lại",
};
// Nhãn cách tính thuế TNCN. `null` KHÔNG có ở đây: null = bị che quyền, xử riêng (ẩn cả dòng).
export const PIT_MODE_LABEL: Record<string, string> = {
  luy_tien: "Luỹ tiến (HĐ ≥ 3 tháng)", khau_tru_10: "Khấu trừ 10%", cam_ket_08: "Cam kết 08/CK-TNCN",
};

export const DANG_TAI = { tt: "dang-tai" } as const;

export const REQ_FIELD_LABEL: Record<string, string> = {
  full_name: "Họ tên", date_of_birth: "Ngày sinh", national_id: "CCCD",
  national_id_date: "Ngày cấp CCCD", national_id_place: "Nơi cấp CCCD",
  permanent_address: "Hộ khẩu", bank_account: "Số tài khoản", bank_name: "Ngân hàng",
  dependents_count: "Người phụ thuộc",
};

export const REQ_PAGE_SIZE = 10;
// Nhãn PILL ngắn ("Chờ duyệt") vì nó là bộ lọc; nhãn BADGE trong bảng mới là câu đủ
// ("Chờ HCNS duyệt") vì nó là trạng thái. Đừng dùng lẫn.
export const REQ_LOC = [
  { key: "pending", label: "Chờ duyệt" },
  { key: "approved", label: "Đã duyệt" },
  { key: "rejected", label: "Từ chối" },
  { key: "cancelled", label: "Đã rút" },
] as const;

// Nhãn `ngan` cho màn hẹp (≤640px) — badge bị bóp còn ~100px, câu đủ sẽ bị cắt giữa chừng.
// `aria-label` của dòng vẫn dùng câu ĐỦ để trình đọc màn hình không mất nghĩa.
export const REQ_STATUS_CONFIG: Record<string, { label: string; ngan: string; cls: string; icon: IconName }> = {
  pending: { label: "Chờ HCNS duyệt", ngan: "Chờ", cls: "badge-sem--amber", icon: "clock" },
  approved: { label: "Đã phê duyệt", ngan: "Đã duyệt", cls: "badge-sem--moss", icon: "check" },
  rejected: { label: "HCNS từ chối", ngan: "Từ chối", cls: "badge-sem--signal", icon: "alert" },
  cancelled: { label: "Đã rút lại", ngan: "Đã rút", cls: "badge-sem--muted", icon: "ban" },
};
