// Nhãn/hằng dùng chung của màn Hồ sơ nhân sự (tách từ pages/NhanSuPage.tsx).

export const STATUS_LABEL: Record<string, string> = {
  probation: "Thử việc",
  // Máy tự đặt khi qua Ngày hết thử việc. KHÔNG phải chính thức — và tiền vẫn là tiền thử việc
  // cho tới khi HCNS bấm "Chuyển chính thức". Nhãn phải nói rõ là đang CHỜ người, nếu không
  // HCNS đọc thành "xong rồi" rồi không bấm nữa.
  probation_ended: "Hết thử việc · chờ xác nhận",
  active: "Chính thức",
  on_leave: "Nghỉ dài hạn",
  suspended: "Đình chỉ",
  resigned: "Đã nghỉ",
};
export const STATUS_CLASS: Record<string, string> = {
  probation: "ns-badge--warn",
  probation_ended: "ns-badge--due",
  active: "ns-badge--ok",
  on_leave: "ns-badge--info",
  suspended: "ns-badge--muted",
  resigned: "ns-badge--danger",
};
export const GENDER_LABEL: Record<string, string> = {
  male: "Nam",
  female: "Nữ",
  other: "Khác",
};
export const DOC_KIND_LABEL: Record<string, string> = {
  hop_dong: "Hợp đồng",
  cccd: "CCCD",
  bang_cap: "Bằng cấp",
  khac: "Khác",
};
export const EVENT_LABEL: Record<string, string> = {
  hired: "Vào làm",
  confirmed: "Chuyển chính thức",
  transferred: "Điều chuyển",
  promoted: "Nâng bậc / đổi chức danh",
  leave_start: "Bắt đầu nghỉ dài hạn",
  leave_end: "Đi làm lại",
  suspended: "Đình chỉ",
  resigned: "Nghỉ việc",
  reinstated: "Tuyển lại",
};

// Hàng đợi HCNS duyệt "yêu cầu cập nhật" của NV.
export const REQ_FIELD_LABEL: Record<string, string> = {
  full_name: "Họ tên",
  date_of_birth: "Ngày sinh",
  national_id: "CCCD",
  national_id_date: "Ngày cấp CCCD",
  national_id_place: "Nơi cấp CCCD",
  permanent_address: "Hộ khẩu",
  bank_account: "Số tài khoản",
  bank_name: "Ngân hàng",
  dependents_count: "Người phụ thuộc",
};
export const REQ_DATE_FIELDS = new Set(["date_of_birth", "national_id_date"]);

export const ACTION_TITLE: Record<string, string> = {
  confirm: "Chuyển chính thức",
  leave_start: "Cho nghỉ dài hạn",
  leave_end: "Đi làm lại",
  suspend: "Đình chỉ",
  resign: "Cho nghỉ việc",
  reinstate: "Tuyển lại",
  transfer: "Điều chuyển phòng/tổ",
  promote: "Nâng bậc / đổi chức danh",
  link: "Nối tài khoản đăng nhập",
  unlink: "Gỡ tài khoản đăng nhập",
};
