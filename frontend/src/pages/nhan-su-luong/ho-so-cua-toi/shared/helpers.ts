// Hàm dùng chung của màn "Hồ sơ của tôi" (tách từ pages/HoSoCuaToiPage.tsx).
//
// ⚠ `fmtDate` / `fmtDateTime` / `fmtSo` ở đây là BẢN CỤC BỘ của màn này, TRÙNG TÊN nhưng KHÁC
// cách hiện so với `utils/format`. Đừng "dọn" bằng cách trỏ sang utils — đổi là lệch cách
// hiển thị của cả màn.
import { ApiError, type EmployeeDetail, type UpdateRequest } from "../../../../api/client";
import type { IconName } from "../../../../components/Icons";
import { REQ_FIELD_LABEL, REQ_LOC, REQ_STATUS_CONFIG } from "./constants";

export function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s : d.toLocaleDateString("vi-VN");
}
export function fmtDateTime(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  return Number.isNaN(d.getTime())
    ? s
    : d.toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
export const fmtSo = (n: number): string => n.toLocaleString("vi-VN");

/** Thâm niên tổng = thâm niên khai TRƯỚC khi vào (tháng) + số tháng từ `hire_date` tới nay.
 *  Bỏ vế đầu là tính hụt với người chuyển từ nơi khác sang. Trả null khi chưa có gì để hiện. */
export function thamNien(priorMonths: number | undefined, hireDate: string | null | undefined): string | null {
  let tuNgayVao = 0;
  if (hireDate) {
    const h = new Date(hireDate);
    if (!Number.isNaN(h.getTime())) {
      const now = new Date();
      tuNgayVao = Math.max(0, (now.getFullYear() - h.getFullYear()) * 12 + (now.getMonth() - h.getMonth()));
    }
  }
  const tong = (priorMonths ?? 0) + tuNgayVao;
  if (tong <= 0) return null;
  return `${Math.floor(tong / 12)} năm ${tong % 12} tháng`;
}

export const nhanLoc = (key: string): string => REQ_LOC.find((f) => f.key === key)?.label ?? key;

/** "4 mục: Nơi cấp CCCD, Hộ khẩu +2" — tóm tắt MỘT DÒNG cho ô bảng.
 *
 *  CHỈ tên trường, KHÔNG bao giờ có giá trị người dùng gõ: giá trị là chuỗi tự do dài vô hạn, và
 *  đó đúng là thứ đã làm tràn bảng hàng đợi HCNS trước đây (xem nhan-su.css §hàng đợi). Giá trị
 *  chỉ hiện trong popup, nơi có chỗ xuống dòng. */
export function tomTatChanges(changes: UpdateRequest["changes"]): { ngan: string; du: string } {
  const ten = Object.keys(changes).map((k) => REQ_FIELD_LABEL[k] ?? k);
  if (ten.length === 0) return { ngan: "Không có mục nào", du: "" };
  const dau = ten.slice(0, 2).join(", ");
  return {
    ngan: `${ten.length} mục: ${dau}${ten.length > 2 ? ` +${ten.length - 2}` : ""}`,
    du: ten.join(", "),
  };
}

/** Giá trị mới của một field, dạng đọc được. `null`/rỗng là ĐỀ NGHỊ XOÁ, không phải thiếu dữ liệu. */
export function giaTriMoi(field: string, v: unknown): string {
  if (v === null || v === "") return "(bỏ trống)";
  if (field === "date_of_birth" || field === "national_id_date") return fmtDate(String(v));
  return String(v);
}

/** Ô còn trống, TÁCH hai nhóm vì dẫn tới hai việc khác nhau: tự điền (modal liên hệ) vs
 *  gửi đề nghị cho HCNS. Cố ý KHÔNG đếm: `dependents_count` (0 là giá trị thật),
 *  `pit_mode` (null = bị che quyền), `probation_end_date` (chỉ có nghĩa khi thử việc). */
export function oThieu(emp: EmployeeDetail | null): { tu: string[]; hcns: string[] } {
  if (!emp) return { tu: [], hcns: [] };
  const trong = (v: unknown) => v === null || v === undefined || v === "";
  const tu = ([
    ["phone", emp.phone], ["email", emp.email], ["current_address", emp.current_address],
    ["emergency_contact_name", emp.emergency_contact_name], ["emergency_contact_phone", emp.emergency_contact_phone],
  ] as const).filter(([, v]) => trong(v)).map(([k]) => k as string);
  const hcns = ([
    ["date_of_birth", emp.date_of_birth], ["gender", emp.gender], ["national_id", emp.national_id],
    ["national_id_date", emp.national_id_date], ["national_id_place", emp.national_id_place],
    ["permanent_address", emp.permanent_address], ["bank_account", emp.bank_account],
    ["bank_name", emp.bank_name], ["social_insurance_no", emp.social_insurance_no],
    ["pit_tax_code", emp.pit_tax_code],
  ] as const).filter(([, v]) => trong(v)).map(([k]) => k as string);
  return { tu, hcns };
}

export function kieuFile(name: string): "pdf" | "img" | "doc" {
  const ext = name.toLowerCase().split(".").pop() ?? "";
  if (ext === "pdf") return "pdf";
  if (["jpg", "jpeg", "png", "gif", "webp", "heic"].includes(ext)) return "img";
  return "doc";
}

export const cfgReq = (status: string) =>
  REQ_STATUS_CONFIG[status] ?? { label: status, ngan: status, cls: "badge-sem--muted", icon: "help" as IconName };

/** Giá trị ĐANG có trên hồ sơ của một field trong `changes` — để so "cũ → mới". */
export function giaTriCu(emp: EmployeeDetail, field: string): string {
  const v = (emp as unknown as Record<string, unknown>)[field];
  if (v === null || v === undefined || v === "") return "";
  if (field === "date_of_birth" || field === "national_id_date") return fmtDate(String(v));
  return String(v);
}

export function messageFor(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.isNetwork) return "Mất kết nối. Vui lòng thử lại.";
    if (err.status >= 500) return "Có lỗi xảy ra, vui lòng thử lại sau.";
    return err.message; // surfaces the backend's Vietnamese detail (400/422)
  }
  return "Đã có lỗi xảy ra. Vui lòng thử lại.";
}
