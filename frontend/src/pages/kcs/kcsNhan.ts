// Nhãn tiếng Việt dùng chung của KCS theo lệnh — màn KCS, ngăn chi tiết bàn tổ, hộp "KCS báo lỗi".
import type { SxKcsKetLuan, SxKcsTrangThaiGuiKho } from "../../api/client";

/** Trạng thái chạy của công đoạn (enum công việc). */
export const KCS_CD_TRANG_THAI: Record<string, string> = {
  released: "Chưa bắt đầu",
  running: "Đang chạy",
  paused: "Tạm dừng",
  completed: "Đã xong",
};

// "Có lỗi" cùng màu gỉ ở mọi chỗ (dòng công đoạn, chip trên thẻ việc, từng lần kiểm); "Không đạt"
// (không cái nào đạt) nặng hơn một bậc.
export const KCS_KET_LUAN: Record<SxKcsKetLuan, { nhan: string; cls: string }> = {
  dat: { nhan: "Đạt", cls: "badge-sem--moss" },
  dat_mot_phan: { nhan: "Có lỗi", cls: "badge-sem--rust" },
  khong_dat: { nhan: "Không đạt", cls: "badge-sem--signal" },
};

export const KCS_TRANG_THAI_GUI_KHO_LABEL: Record<SxKcsTrangThaiGuiKho, string> = {
  chua_gui: "Chưa gửi kho",
  dang_cho: "Đang chờ kho nhận",
  da_nhap: "Đã nhập kho",
  khong_ap_dung: "Không áp dụng",
};

/** Trạng thái yêu cầu NHẬP kho thành phẩm — chính là trạng thái của yêu cầu ở màn Yêu cầu nhập
 *  xuất (tạo là `approved` ngay, kho ghi sổ phiếu nhập tới đâu thì `partial` / `done` tới đó). */
export const KCS_YC_KHO_TRANG_THAI: Record<string, { nhan: string; cls: string }> = {
  draft: { nhan: "Nháp", cls: "badge-sem--muted" },
  pending: { nhan: "Chờ duyệt", cls: "badge-sem--amber" },
  approved: { nhan: "Chờ kho nhận", cls: "badge-sem--amber" },
  received: { nhan: "Kho đã tiếp nhận", cls: "badge-sem--steel" },
  preparing: { nhan: "Kho đang lập phiếu", cls: "badge-sem--steel" },
  partial: { nhan: "Kho đã nhận một phần", cls: "badge-sem--steel" },
  done: { nhan: "Kho đã nhận đủ", cls: "badge-sem--moss" },
  rejected: { nhan: "Kho từ chối", cls: "badge-sem--signal" },
  cancelled: { nhan: "Đã hủy", cls: "badge-sem--muted" },
};

/** Máy chủ chỉ nhận lần kiểm khi công đoạn đã bắt đầu (đang chạy / tạm dừng / đã xong). */
export function kiemDuoc(trangThai: string): boolean {
  return trangThai === "running" || trangThai === "paused" || trangThai === "completed";
}

/** Trạng thái nhóm thành phẩm của lệnh. */
export const KCS_NHOM_TRANG_THAI: Record<string, { nhan: string; cls: string }> = {
  in_production: { nhan: "Đang sản xuất", cls: "badge-sem--steel" },
  waiting_conditions: { nhan: "Chờ điều kiện", cls: "badge-sem--amber" },
  closed_full: { nhan: "Đã đóng đủ", cls: "badge-sem--moss" },
  closed_short: { nhan: "Đã đóng thiếu", cls: "badge-sem--muted" },
};

/** Tình trạng kiểm của một công đoạn theo các lần kiểm đã ghi: chưa kiểm · đạt · có lỗi. */
export function tinhTrangKiem(soLan: number, tongLoi: number): { nhan: string; cls: string; loai: "chua" | "dat" | "loi" } {
  if (soLan <= 0) return { nhan: "Chưa kiểm", cls: "badge-sem--muted", loai: "chua" };
  if (tongLoi > 0) return { nhan: `Có lỗi · ${soLan} lần`, cls: "badge-sem--rust", loai: "loi" };
  return { nhan: `Đạt · ${soLan} lần`, cls: "badge-sem--moss", loai: "dat" };
}
