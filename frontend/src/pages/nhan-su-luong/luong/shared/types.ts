// Kiểu dùng chung của màn Lương (tách từ pages/LuongPage.tsx).
import type { ComponentKind } from "../../../../api/client";

// `"khoan"` GỠ 17/08/2026: bảng đơn giá khoán thành màn "Công việc khoán" của Cấu hình danh mục.
// Giữ giá trị này trong union thì `?tab=khoan` (link cũ ai đó bookmark) vào một tab không render gì.
// Không có nó, `tabTuUrl` rơi về tab mặc định — người dùng thấy màn Lương bình thường.
export type Tab =
  | "bang"
  | "nhanvien"
  | "tamung"
  | "cauhinh"
  | "phieu"
  | "tamung-me";

/** TẦNG 2 — một khoản ĐANG ĐƯỢC GÁN cho NV (`employee_salary_components`), hiện ở modal Sửa
 *  lương. Bảng này CHỈ chứa khoản đang gán, không đổ phẳng cả danh mục: muốn thêm thì bấm
 *  "+ Thêm khoản thu nhập" và CHỌN từ danh mục gốc (quy trình 2 bước — không gõ tên tự do).
 *
 *  `saved`/`savedNote` = số đang nằm trên server (`saved === null` ⇒ dòng vừa chọn, CHƯA lưu)
 *  ⇒ chỉ gửi dòng nào lệch. `is_taxable` chép từ danh mục gốc, CHỈ ĐỌC ở đây. */
export type CompRow = {
  component_id: number;
  name: string;
  kind: ComponentKind;
  is_taxable: boolean;
  /** false = danh mục đã NGỪNG ÁP DỤNG mà người này còn giữ ⇒ cảnh báo đỏ, tiền VẪN trả. */
  is_active: boolean;
  saved: number | null;
  savedNote: string | null;
  draft: number;
  note: string;
};

/** Ô lương HỆ THỐNG — bảng RIÊNG, KHÔNG trộn với khoản danh mục (chốt chủ 27/07/2026): nguồn
 *  số là `employee_salaries` chứ không phải danh mục, nên sửa được SỐ TIỀN nhưng KHÔNG gỡ
 *  được, và cờ chịu thuế do ENGINE quyết (đọc `payroll_service._compute` / `_auto_pit`).
 *
 *  `taxable` phải khớp engine, không đoán:
 *   · lương cơ bản + trách nhiệm → `luong_cong` ⇒ CHỊU thuế
 *   · chuyên cần                → `chuyen_can` ⇒ CHỊU thuế
 *   · phụ cấp thâm niên         → ⊂ `allowance` ⇒ CHỊU thuế
 *   · phụ cấp ca                → đi qua `night_pay`, `_auto_pit` TRỪ khỏi thu nhập chịu thuế
 *                                 (miễn như tăng ca/ca đêm) ⇒ MIỄN thuế */
export type SysRow = {
  key: string;
  name: string;
  note: string;
  taxable: boolean;
  value: number;
  set: (v: number) => void;
  /** Khoản đã NGƯNG: cho xem số cũ để tra lịch sử nhưng không cho sửa (sửa cũng không ra tiền). */
  readOnly?: boolean;
};
