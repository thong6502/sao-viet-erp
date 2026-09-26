// Lọc · đếm · chọn của tab Tạm ứng ở quy mô nhà máy (~1000 người) — chủ chốt 25/09/2026.
//
// • Tab TRẠNG THÁI: Chờ duyệt · Chờ chi · Đã chi · Từ chối/Huỷ (+ Tất cả). Mỗi tab một loại việc
//   (duyệt/từ chối — lập phiếu chi/xuất Excel) nên lựa chọn không bao giờ trộn hai việc.
// • Bộ lọc LOẠI (tạm ứng / lương đợt 1) · TỔ · ô tìm (tên, mã NV, mã phiếu — gõ không dấu được).
// • LỰA CHỌN: đổi trang / loại / tổ / gõ tìm ⇒ GIỮ (chọn tạm ứng rồi sang đợt 1 chọn tiếp, duyệt
//   một lượt); đổi KỲ hoặc đổi TAB ⇒ XOÁ. Phiếu đã chọn mà bộ lọc đang che thì thanh chọn nói rõ số,
//   hộp xác nhận tách theo loại — không ai duyệt nhầm tiền mình không nhìn thấy.
// • Tải CẢ KỲ một lần rồi lọc + chia trang ở trình duyệt (như Bảng công tháng): vài nghìn dòng vẫn
//   nhẹ, và "chọn tất cả N phiếu đang lọc" đi qua mọi trang mà không phải hỏi máy chủ.
import type { SalaryAdvance } from "../../../../api/client";
import { khopGanDung } from "../../../../utils/timGanDung";
import { money } from "../shared/helpers";

export type TabTrangThai = "tat_ca" | "cho_duyet" | "cho_chi" | "da_chi" | "tu_choi";
export type LocLoai = "tat_ca" | "tam_ung" | "luong_dot_1";

export interface BoLocTamUng {
  loai: LocLoai;
  /** `department_id` dạng chuỗi; "" = mọi tổ. */
  to: string;
  tim: string;
}

export const BO_LOC_TRONG: BoLocTamUng = { loai: "tat_ca", to: "", tim: "" };
export const CO_TRANG = 50;

export const TAB_TRANG_THAI: { key: TabTrangThai; nhan: string }[] = [
  { key: "tat_ca", nhan: "Tất cả" },
  { key: "cho_duyet", nhan: "Chờ duyệt" },
  { key: "cho_chi", nhan: "Chờ chi" },
  { key: "da_chi", nhan: "Đã chi" },
  { key: "tu_choi", nhan: "Từ chối / Huỷ" },
];

/** Phiếu thuộc tab trạng thái nào. "Chờ chi" = đã duyệt mà CHƯA có phiếu chi. */
export function thuocTab(a: SalaryAdvance, tab: TabTrangThai): boolean {
  switch (tab) {
    case "cho_duyet":
      return a.status === "pending";
    case "cho_chi":
      return a.status === "approved" && !a.phieu_chi_id;
    case "da_chi":
      return a.status === "paid" || (a.status === "approved" && !!a.phieu_chi_id);
    case "tu_choi":
      return a.status === "rejected" || a.status === "cancelled";
    default:
      return true;
  }
}

export function khopBoLoc(a: SalaryAdvance, loc: BoLocTamUng): boolean {
  if (loc.loai !== "tat_ca" && (a.kind || "tam_ung") !== loc.loai) return false;
  if (loc.to && String(a.department_id ?? "") !== loc.to) return false;
  return khopGanDung(`${a.employee_name ?? ""} ${a.employee_code ?? ""} ${a.code ?? ""}`, loc.tim);
}

/** Số phiếu mỗi tab SAU bộ lọc loại / tổ / tìm — số in trên nhãn tab. */
export function demTheoTab(items: SalaryAdvance[], loc: BoLocTamUng): Record<TabTrangThai, number> {
  const dem: Record<TabTrangThai, number> = {
    tat_ca: 0, cho_duyet: 0, cho_chi: 0, da_chi: 0, tu_choi: 0,
  };
  for (const a of items) {
    if (!khopBoLoc(a, loc)) continue;
    for (const t of TAB_TRANG_THAI) if (thuocTab(a, t.key)) dem[t.key] += 1;
  }
  return dem;
}

/** Tổ có mặt trong danh sách kỳ — nguồn ô "Tất cả tổ". */
export function dsTo(items: SalaryAdvance[]): { id: string; ten: string }[] {
  const m = new Map<string, string>();
  for (const a of items) {
    if (a.department_id != null) m.set(String(a.department_id), a.department_name ?? `Tổ #${a.department_id}`);
  }
  return [...m.entries()].map(([id, ten]) => ({ id, ten })).sort((x, y) => x.ten.localeCompare(y.ten, "vi"));
}

/** "200 tạm ứng · 150 lương đợt 1 — tổng 875.000.000đ" cho hộp xác nhận thao tác nhiều phiếu. */
export function tachLoai(advs: SalaryAdvance[]): string {
  const tu = advs.filter((a) => (a.kind || "tam_ung") !== "luong_dot_1").length;
  const d1 = advs.length - tu;
  const phan = [tu ? `${tu} tạm ứng` : "", d1 ? `${d1} lương đợt 1` : ""].filter(Boolean);
  return `${phan.join(" · ")} — tổng ${money(advs.reduce((s, a) => s + a.amount, 0))}đ`;
}
