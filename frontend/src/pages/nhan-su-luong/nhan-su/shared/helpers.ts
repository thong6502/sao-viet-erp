// Hàm thuần (không JSX, không state) của màn Hồ sơ nhân sự (tách từ pages/NhanSuPage.tsx).
import {
  ApiError,
  EMPLOYEE_FIELD_MAXLEN,
  type EmployeeMeta,
  type EmployeeRow,
  type UpdateRequest,
} from "../../../../api/client";
import { fmtDate } from "../../../../utils/format";
import { File, FileText, Image } from "lucide-react";
import { REQ_DATE_FIELDS, REQ_FIELD_LABEL } from "./constants";

export function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  return "Có lỗi xảy ra.";
}

export function isEndingSoon(e: EmployeeRow): boolean {
  if (e.status !== "probation" || !e.probation_end_date) return false;
  const end = new Date(e.probation_end_date).getTime();
  const now = Date.now();
  return end >= now && end <= now + 30 * 24 * 3600 * 1000; // khớp KPI backend (30 ngày)
}

export function getAvatarClass(name: string): string {
  const firstChar = name.trim().slice(0, 1).toLowerCase();
  const validChars = [
    "a",
    "b",
    "c",
    "d",
    "e",
    "g",
    "h",
    "k",
    "l",
    "m",
    "n",
    "p",
    "q",
    "s",
    "t",
    "u",
    "v",
    "x",
  ];
  if (validChars.includes(firstChar)) return `ns2-row__av--${firstChar}`;
  return "ns2-row__av--default";
}

// --- Bậc tay nghề (danh mục `job_grades`) ----------------------------------
// Bậc CHỈ để khai: không mang tiền, không hệ số. Chỉ khối SẢN XUẤT mới khai.

/** Có hiện ô "Bậc tay nghề" cho phòng/tổ này không. `la_san_xuat` là cờ HIỆU LỰC — backend đã
 *  leo cây cha-con nên FE không phải tự suy. Chưa ai tick cờ ở đâu ⇒ hiện cho MỌI phòng: thà
 *  thừa một ô còn hơn giấu mất đường khai bậc của cả nhà máy. */
export function isProduction(
  meta: EmployeeMeta | null,
  deptId: number | null | undefined,
): boolean {
  if (!meta) return false;
  const marked = meta.departments.some((d) => d.la_san_xuat);
  if (!marked) return true;
  return meta.departments.find((d) => d.id === deptId)?.la_san_xuat ?? false;
}

/** Một giá trị trong đề nghị → chuỗi đọc được. `null`/rỗng phải nói RÕ là "chưa có" hay "bỏ
 *  trống" chứ không in ô trắng: người duyệt đang phải quyết dựa trên đúng mấy chữ này. */
export function reqValue(field: string, v: unknown, khiRong: string): string {
  if (v === null || v === undefined || v === "") return khiRong;
  return REQ_DATE_FIELDS.has(field) ? fmtDate(String(v)) : String(v);
}

/** Ô nào vượt độ dài cột hồ sơ ⇒ bấm Duyệt chắc chắn bị BE chặn. Nói trước cho người duyệt
 *  (và tắt nút Duyệt) thay vì để họ bấm rồi ăn thông báo lỗi. */
export function reqQuaDai(changes: UpdateRequest["changes"]): string[] {
  const loi: string[] = [];
  for (const [k, v] of Object.entries(changes)) {
    const max = EMPLOYEE_FIELD_MAXLEN[k];
    if (max && typeof v === "string" && v.length > max) {
      loi.push(`${REQ_FIELD_LABEL[k] ?? k}: ${v.length} ký tự, vượt giới hạn ${max}`);
    }
  }
  return loi;
}

export function getFileTypeInfo(fileName: string) {
  const ext = fileName.split(".").pop()?.toLowerCase();
  if (ext === "pdf") {
    return { icon: FileText, className: "ns-fileitem__icon--pdf" };
  }
  if (["png", "jpg", "jpeg", "webp", "gif", "svg"].includes(ext || "")) {
    return { icon: Image, className: "ns-fileitem__icon--img" };
  }
  return { icon: File, className: "ns-fileitem__icon--doc" };
}

export function formatFileSize(bytes?: number): string | null {
  if (!bytes) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** "Thâm niên hiện tại: X năm Y tháng" (chỉ để xem) = thâm niên khai trước khi vào (đổi ra
 *  tháng) + số tháng từ ngày vào tới nay. Trả null khi chưa có gì để hiện. */
export function seniorityLabel(
  priorYears: number,
  hireDate?: string | null,
): string | null {
  const prior = Math.round((priorYears || 0) * 12);
  let fromHire = 0;
  if (hireDate) {
    const h = new Date(hireDate);
    if (!Number.isNaN(h.getTime())) {
      const now = new Date();
      fromHire = Math.max(
        0,
        (now.getFullYear() - h.getFullYear()) * 12 +
          (now.getMonth() - h.getMonth()),
      );
    }
  }
  const total = prior + fromHire;
  if (total <= 0) return null;
  return `Thâm niên hiện tại: ${Math.floor(total / 12)} năm ${total % 12} tháng`;
}

/** Mật khẩu tạm dễ đọc (bỏ 0/O/1/l/I để khỏi đọc nhầm khi bàn giao). */
export function genPassword(len = 12): string {
  const chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789";
  const buf = new Uint32Array(len);
  crypto.getRandomValues(buf);
  return Array.from(buf, (n) => chars[n % chars.length]).join("");
}

export function deviceLabel(ua: string | null): string {
  if (!ua) return "Thiết bị không rõ";
  const browser = /Edg\//.test(ua)
    ? "Edge"
    : /Chrome\//.test(ua)
      ? "Chrome"
      : /Safari\//.test(ua)
        ? "Safari"
        : /Firefox\//.test(ua)
          ? "Firefox"
          : "Trình duyệt khác";
  const os = /Windows/.test(ua)
    ? "Windows"
    : /Mac OS/.test(ua)
      ? "macOS"
      : /Android/.test(ua)
        ? "Android"
        : /iPhone|iPad/.test(ua)
          ? "iOS"
          : "Hệ khác";
  return `${browser} · ${os}`;
}
