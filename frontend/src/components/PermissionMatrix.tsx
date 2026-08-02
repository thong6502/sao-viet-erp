// Permission matrix — modules × (Xem / Chỉnh sửa / Phạm vi) + quyền chi tiết. Presentational +
// controlled: the parent owns the rows and gets toggle/scope callbacks. Shared by the Roles
// screen and the per-department "Vai trò & Quyền" panel so both edit permissions identically.
//
// Trình bày (redesign): gom module theo PHÂN HỆ (accordion thu gọn được); mỗi module là một
// hàng với công tắc Xem / Chỉnh sửa / pill Phạm vi; module có quyền chi tiết hiện chip "N/M chi
// tiết" → bấm BUNG INLINE ngay dưới hàng (không popover portal). Data contract KHÔNG đổi.
import { useState } from "react";
import type { ModuleDef, PermissionRow, Scope } from "../api/client";
import { Icon } from "./Icons";
import "./permission-matrix.css";

export const ACTIONS = [
  { key: "can_read", label: "Xem" },
  { key: "can_create", label: "Thêm" },
  { key: "can_update", label: "Sửa" },
  { key: "can_delete", label: "Xóa" },
] as const;

export type ActionKey =
  | "can_read"
  | "can_create"
  | "can_update"
  | "can_delete"
  // Quyền chi tiết (Cách B).
  | "can_reassign"
  | "can_export"
  | "can_view_debt"
  | "can_view_discount"
  | "can_approve"
  | "can_manage_status"
  | "can_reset_password"
  | "can_lock"
  | "can_revoke_sessions"
  | "can_assign_role"
  | "can_transfer"
  | "can_set_head"
  | "can_requote"
  | "can_manage_price"
  | "can_cancel"
  | "can_manage_permissions"
  | "can_clone"
  | "can_toggle_active"
  | "can_reparent"
  | "can_view_salary"
  | "can_adjust"
  | "can_approve_exception"
  | "can_set_credit_terms"
  | "can_record_deposit"
  | "can_assign_work"
  | "can_record_output"
  | "can_handover"
  | "can_request"
  | "can_view_stock"
  | "can_view_cost"
  | "can_set_threshold"
  | "can_post";

// UI gộp Thêm/Sửa/Xóa thành một công tắc "quyền chỉnh sửa": tick là bật cả ba.
// Dữ liệu vẫn lưu tách (can_create/can_update/can_delete) nên backend không đổi.
const WRITE_ACTIONS: ActionKey[] = ["can_create", "can_update", "can_delete"];

// Quyền CHI TIẾT khai báo theo từng module (Cách B). Module không có tên ở đây → không hiện
// cột chi tiết. Thêm module/hành động mới chỉ cần bổ sung vào bảng này + cột ở backend.
// `keys` (tuỳ chọn): 1 công tắc bật/tắt NHIỀU cột cùng lúc (gộp quyền). `key` = cột đại diện để
// đếm/định danh; `keys` = toàn bộ cột được set. Không có `keys` → công tắc 1 cột như thường.
const FINE_ACTIONS: Record<
  string,
  { key: ActionKey; keys?: ActionKey[]; label: string; hint?: string }[]
> = {
  khach_hang: [
    {
      key: "can_reassign",
      label: "Điều chuyển",
      hint: "Chuyển khách sang NV sale khác (đổi người phụ trách) — một khách hoặc hàng loạt. Không có cờ này thì chỉ xem/sửa khách trong phạm vi của mình, không sang tay được.",
    },
    {
      key: "can_export",
      label: "Xuất file",
      hint: "Xuất danh bạ khách (CSV) + lịch sử mua hàng của khách (Excel). Lịch sử báo giá chưa có nút xuất — BE chưa làm endpoint.",
    },
    {
      key: "can_view_debt",
      label: "Xem công nợ",
      hint: 'Cho xem thẻ Công nợ của khách (số dư phải thu + hạn mức đã dùng). ⚠️ Module Công nợ (AR) CHƯA build — bật quyền vẫn chỉ hiện thẻ "chưa khả dụng", chưa có số thật; chỉ có tác dụng khi module Công nợ hoàn thành.',
    },
    {
      key: "can_set_credit_terms",
      label: "Thiết lập chính sách tài chính",
      hint: 'Sửa chính sách tài chính khách: hạn mức công nợ + số ngày công nợ tối đa (từ ngày xuất HĐ) + rào chiết khấu/biên min–max. Ai cũng XEM, chỉ cờ này mới SỬA. Đây là rào mà "Duyệt báo giá đặc thù" dùng để chặn báo giá vượt ngưỡng.',
    },
  ],
  // Báo giá: thao tác vòng đời THƯỜNG (gửi khách · ghi nhận Khách đồng ý/từ chối · hủy · PDF · tạo bản mới)
  // KHÔNG tách quyền chi tiết — ai có "Sửa" báo giá đều làm được (chủ đầu tư chốt P8). Quyền chi tiết DUY NHẤT
  // còn lại = DUYỆT BÁO GIÁ ĐẶC THÙ (biên thấp / giá trị cao): chỉ vai bật cờ này mới duyệt được đơn trình lên.
  bao_gia: [
    {
      key: "can_approve_exception",
      label: "Duyệt báo giá đặc thù",
      hint: 'Duyệt / từ chối báo giá "đặc thù" — báo giá biên thấp hoặc vượt rào chiết khấu/biên (đặt ở chính sách tài chính khách) mà sale trình lên; duyệt xong mới gửi khách được. Loại thường thì ai Sửa được báo giá đều làm; riêng loại đặc thù cần cờ này. Thường chỉ TP/GĐ Kinh doanh.',
    },
  ],
  // Đơn hàng bán: duyệt đơn đặc thù (nhập tay/bổ sung) + hủy đơn đã chốt = 1 cờ; ghi cọc = Kế toán.
  don_hang_ban: [
    {
      key: "can_approve_exception",
      label: "Duyệt đơn đặc thù · hủy đơn đã chốt",
      hint: 'Gộp 2 quyền vào 1 cờ: (1) Duyệt "đơn đặc thù" — đơn nhập tay KHÔNG có giá vốn nên không soi được biên lời/lỗ, Sale phải trình lên; (2) Hủy đơn ĐÃ CHỐT (đã lên trạng thái "ordered"). Thường chỉ TP/GĐ Kinh doanh có — NV Sales không.',
    },
    {
      key: "can_record_deposit",
      label: "Ghi phiếu thu cọc",
      hint: 'Ghi / sửa / xóa phiếu thu tiền cọc của khách trên đơn (tiền mặt hoặc chuyển khoản, có đối chiếu). Tách riêng cho Kế toán bán hàng — Sale lập đơn nhưng KHÔNG tự ghi tiền cọc (chống "tự thu tự chốt").',
    },
  ],
  san_xuat: [
    {
      key: "can_assign_work",
      label: "Gán việc (tổ trưởng)",
      hint: "Tổ trưởng gán thợ vào công đoạn của lệnh đã phát. Vai có cờ này (hoặc phạm vi Cả phòng/Tất cả) thấy TOÀN BỘ lệnh của tổ + nút gán; thợ được gán mới hứng thông báo + xem lệnh của mình.",
    },
    {
      key: "can_record_output",
      label: "Ghi sản lượng",
      hint: "Tổ trưởng ghi sản lượng ĐẠT/HỎNG cho công đoạn của tổ (cộng dồn nhiều đợt, ghi nhận — không chặn). Thợ chỉ xem.",
    },
    {
      key: "can_handover",
      label: "Bàn giao / nhận",
      hint: "Tổ trưởng GIAO số sang tổ kế + XÁC NHẬN NHẬN (2 con dấu, lệch được để truy thất thoát). Không gate cứng chặn tổ nhận chạy.",
    },
  ],
  vai_tro: [{ key: "can_manage_permissions", label: "Sửa ma trận phân quyền" }],
  nguoi_dung: [
    { key: "can_reset_password", label: "Đặt lại mật khẩu" },
    { key: "can_lock", label: "Khóa / Mở tài khoản" },
    { key: "can_revoke_sessions", label: "Thu hồi phiên" },
    { key: "can_assign_role", label: "Gán vai trò" },
    { key: "can_transfer", label: "Chuyển phòng ban" },
  ],
  phong_ban: [
    { key: "can_set_head", label: "Đặt trưởng phòng" },
    { key: "can_reparent", label: "Đổi cấp trên (cây tổ chức)" },
  ],
  // Kho: 3 ô chi tiết + công tắc chung Xem (can_read) + Chỉnh sửa (= LẬP PHIẾU).
  //   · Tạo đề nghị (can_request) — người XIN nhập/lĩnh vật tư.
  //   · Duyệt đề nghị (can_approve) — quản lý bộ phận ĐỀ NGHỊ (KHÔNG phải kho).
  //   · Xem kho (1 công tắc = 3 cột): xem tồn + xem giá vốn + khai ngưỡng.
  //   · Ghi sổ phiếu (can_post) — TÁCH riêng để giữ SoD: Thủ kho lập phiếu NHƯNG KHÔNG ghi sổ.
  // Vai KHO (cấp phát) bật "Xem kho" + Lập phiếu; chỉ QL kho / Kế toán kho thêm "Ghi sổ".
  // KHÔNG có Duyệt (kho không tự duyệt).
  kho: [
    {
      key: "can_request",
      label: "Tạo đề nghị nhập/xuất",
      hint: "Lập ĐỀ NGHỊ nhập/xuất kho (tổ SX xin lĩnh vật tư, mua hàng xin nhập bổ sung). Người đề nghị nên để phạm vi \"Của tôi\".",
    },
    {
      key: "can_approve",
      label: "Duyệt đề nghị",
      hint: "Duyệt / từ chối đề nghị kho (được cắt bớt số lượng khi duyệt). Của QUẢN LÝ BỘ PHẬN đề nghị (vd Quản lý sản xuất duyệt đề nghị của tổ), KHÔNG phải kho — kho chỉ nhận đề nghị đã duyệt rồi cấp. Không ai tự duyệt đề nghị của chính mình.",
    },
    {
      key: "can_view_stock",
      keys: ["can_view_stock", "can_view_cost", "can_set_threshold"],
      label: "Xem kho (xem tồn/giá vốn · ngưỡng)",
      hint: "MỘT công tắc gộp 3 quyền XEM/QUẢN của kho: XEM số tồn · XEM giá vốn & giá trị tồn · KHAI ngưỡng tồn. Thủ kho / QL kho / Kế toán kho bật ô này. KHÔNG gồm Ghi sổ (tách riêng bên dưới) và KHÔNG kèm Duyệt đề nghị.",
    },
    {
      key: "can_post",
      label: "Ghi sổ phiếu (chốt tồn)",
      hint: "GHI SỔ phiếu nhập/xuất → tồn kho THAY ĐỔI THẬT (và Hủy phiếu). TÁCH khỏi Lập phiếu để giữ SoD: Thủ kho lập phiếu nháp, QL kho / Kế toán kho vào xem rồi Ghi sổ hoặc Hủy. Người cầm hàng khác người chốt sổ.",
    },
  ],
  dm_giay_vat_tu: [
    { key: "can_manage_price", label: "Cập nhật bảng giá" },
    { key: "can_clone", label: "Nhân bản" },
    { key: "can_toggle_active", label: "Bật/tắt hoạt động" },
  ],
  dm_thiet_bi: [{ key: "can_manage_price", label: "Cập nhật đơn giá" }],
  dm_cong_doan: [{ key: "can_manage_price", label: "Cập nhật đơn giá" }],
  nhan_su: [
    { key: "can_view_salary", label: "Xem lương & BHXH (dữ liệu nhạy cảm)" },
    { key: "can_manage_status", label: "Thao tác vòng đời (chính thức/nghỉ/đình chỉ)" },
    { key: "can_transfer", label: "Điều chuyển & nâng bậc" },
    { key: "can_approve", label: "Duyệt yêu cầu cập nhật" },
    { key: "can_export", label: "Xuất Excel danh sách" },
    { key: "can_adjust", label: "Chấm công: chấm bù / sửa công" },
  ],
  di_muon: [
    {
      key: "can_approve",
      label: "Duyệt phiếu đi muộn / về sớm",
      hint: "Duyệt / từ chối phiếu đi muộn · về sớm · nghỉ nửa buổi của người khác (và khai hộ cho thợ — khai hộ là duyệt luôn). Kết hợp Phạm vi: 'Cả phòng' = tổ trưởng chỉ đụng được người trong tổ mình + các tổ con; 'Tất cả' = HCNS duyệt toàn công ty. KHÔNG cần cờ này để nhân viên tự xin/hủy phiếu của chính mình.",
    },
  ],
  tang_ca: [
    {
      key: "can_approve",
      label: "Duyệt phiếu tăng ca",
      hint: "Duyệt / từ chối phiếu tăng ca của người khác (và tạo hộ cho thợ — tạo hộ là duyệt luôn). Kết hợp Phạm vi: 'Cả phòng' = tổ trưởng chỉ đụng được người trong tổ mình + các tổ con; 'Tất cả' = HCNS duyệt toàn công ty. KHÔNG cần cờ này để nhân viên tự gửi/hủy phiếu của chính mình.",
    },
  ],
  luong: [
    {
      key: "can_view_salary",
      label: "Xem cấu hình lương",
      hint: "Cho xem thang bậc, khung lương, KPI, phụ cấp, bảo hiểm và lịch sử lương nhân viên. Không cần cấp quyền này để nhân viên xem Phiếu lương của tôi.",
    },
    { key: "can_approve", label: "Duyệt tạm ứng" },
    { key: "can_lock", label: "Chốt kỳ lương" },
    { key: "can_export", label: "Xuất bảng lương / file chuyển khoản" },
  ],
  ke_toan: [
    { key: "can_approve", label: "Duyệt PMH & lập Phiếu chi/UNC" },
    { key: "can_manage_status", label: "Xác nhận đã chi" },
    { key: "can_cancel", label: "Hủy chứng từ chờ chi" },
    { key: "can_export", label: "In / xuất chứng từ" },
  ],
};

// Giải thích NGẮN cho từng module: bật "Xem" / "Chỉnh sửa" thì người dùng làm được gì. Hiện qua
// dấu ⓘ cạnh tên module (cùng khuôn tooltip với quyền chi tiết). Module không khai ở đây thì
// không hiện ⓘ — thà thiếu còn hơn mô tả sai.
const MODULE_HINTS: Record<string, string> = {
  nhan_su:
    "Xem: mở Hồ sơ nhân sự + Chấm công (danh sách NV, bảng công tháng). Chỉnh sửa: thêm/sửa/xóa hồ sơ nhân viên. Lương & BHXH của NV bị che riêng — muốn thấy phải bật quyền chi tiết “Xem lương & BHXH”.",
  nghi_phep:
    "Xem: thấy đơn nghỉ trong phạm vi được cấp. Chỉnh sửa: quản danh mục loại nghỉ. Nhân viên tự gửi và tự hủy đơn của mình thì KHÔNG cần cấp gì thêm.",
  tang_ca:
    "Xem: thấy mục Tăng ca trên thanh bên + danh sách phiếu trong phạm vi. Nhân viên tự gửi / tự hủy phiếu của chính mình thì KHÔNG cần cấp quyền nào. Muốn DUYỆT phiếu người khác thì bật quyền chi tiết “Duyệt phiếu tăng ca”.",
  di_muon:
    "Xem: thấy danh sách phiếu đi muộn / về sớm / nghỉ nửa buổi trong phạm vi (tab nằm trong màn Chấm công). Nhân viên tự xin / tự hủy phiếu của CHÍNH MÌNH thì KHÔNG cần cấp quyền nào — tab luôn hiện. Muốn DUYỆT phiếu người khác (và khai hộ thợ) thì bật quyền chi tiết “Duyệt phiếu đi muộn / về sớm”.",
  luong:
    "Xem: mở màn Lương (bảng lương tháng, tạm ứng). Chỉnh sửa: tính lại lương, sửa dòng lương, khai cấu hình. Cấu hình lương + duyệt tạm ứng + chốt kỳ + xuất file nằm ở quyền chi tiết. Nhân viên xem “Phiếu lương của tôi” thì không cần quyền này.",
  khach_hang:
    "Xem: danh bạ khách + lịch sử giao dịch. Chỉnh sửa: thêm/sửa/xóa khách. Điều chuyển sang sale khác, xuất file, xem công nợ, đặt chính sách tài chính nằm ở quyền chi tiết.",
  bao_gia:
    "Xem: xem báo giá trong phạm vi. Chỉnh sửa: tạo/sửa báo giá + thao tác vòng đời thường (gửi khách, ghi nhận đồng ý/từ chối, hủy, xuất PDF, tạo bản mới). Riêng báo giá “đặc thù” cần quyền chi tiết để duyệt.",
  don_hang_ban:
    "Xem: xem đơn hàng bán. Chỉnh sửa: tạo/sửa đơn. Duyệt đơn đặc thù, hủy đơn đã chốt và ghi phiếu thu cọc nằm ở quyền chi tiết.",
  san_xuat:
    "Xem: mở hộp việc / lệnh sản xuất trong phạm vi. Chỉnh sửa: cấu hình và phát lệnh. Gán thợ, ghi sản lượng, bàn giao giữa tổ nằm ở quyền chi tiết.",
  vai_tro:
    "Xem: xem danh sách vai trò và ma trận quyền. Chỉnh sửa: thêm/sửa/xóa vai trò. Muốn SỬA được chính ma trận này thì cần quyền chi tiết “Sửa ma trận phân quyền”.",
  nguoi_dung:
    "Xem: danh sách tài khoản. Chỉnh sửa: tạo/sửa tài khoản. Đặt lại mật khẩu, khóa tài khoản, thu hồi phiên, gán vai trò, chuyển phòng ban nằm ở quyền chi tiết.",
  phong_ban:
    "Xem: xem cây tổ chức phòng ban / tổ. Chỉnh sửa: thêm/sửa/xóa phòng ban. Đặt trưởng phòng và đổi cấp trên trong cây nằm ở quyền chi tiết.",
  ke_toan:
    "Xem: xem chứng từ kế toán. Chỉnh sửa: nhập/sửa chứng từ. Duyệt PMH, lập phiếu chi/UNC, xác nhận đã chi, hủy chứng từ, in/xuất nằm ở quyền chi tiết.",
};

// Nghĩa CHUNG của 3 cột — luôn đúng với mọi module, hiện ở dòng tiêu đề.
const COL_HINTS = {
  read: "Cho phép MỞ và ĐỌC dữ liệu của module này. Tắt “Xem” thì mục đó biến mất khỏi thanh bên trái.",
  write: "Gộp 3 quyền Thêm + Sửa + Xóa. Bật là được tạo mới, sửa và xóa dữ liệu — trong giới hạn của cột Phạm vi.",
  scope: "Giới hạn được đụng tới bao nhiêu dữ liệu: “Của tôi” = chỉ bản ghi của chính mình · “Cả phòng” = phòng/tổ mình và mọi tổ con · “Tất cả” = toàn công ty.",
};

export const SCOPES: { value: Scope; label: string }[] = [
  { value: "own", label: "Của tôi" },
  { value: "department", label: "Cả phòng" },
  { value: "all", label: "Tất cả" },
];

// Gom module theo PHÂN HỆ để ma trận quyền đọc được (thu gọn từng nhóm). Module không nằm trong
// nhóm nào rơi vào "Khác" (fallback an toàn khi backend thêm module mới chưa map).
const MODULE_GROUPS: { key: string; label: string; modules: string[] }[] = [
  {
    key: "kinh_doanh",
    label: "Kinh doanh",
    modules: ["khach_hang", "bao_gia", "don_hang_ban", "tinh_gia_thanh"],
  },
  { key: "san_xuat", label: "Sản xuất", modules: ["san_xuat"] },
  { key: "kho", label: "Kho", modules: ["kho", "thu_mua"] },
  { key: "ke_toan", label: "Kế toán", modules: ["ke_toan"] },
  { key: "nhan_su", label: "Nhân sự", modules: ["nhan_su", "nghi_phep", "tang_ca", "di_muon", "luong"] },
  {
    key: "danh_muc",
    label: "Danh mục",
    modules: ["dm_loai_san_pham", "dm_giay_vat_tu", "dm_thiet_bi", "dm_cong_doan", "khuon_be"],
  },
  {
    key: "he_thong",
    label: "Hệ thống",
    modules: ["dashboard", "phong_ban", "vai_tro", "nguoi_dung", "activity_log"],
  },
];

/** A fresh all-off matrix (scope "own") for every module — used when creating a new role. */
export function defaultMatrix(modules: ModuleDef[]): PermissionRow[] {
  return modules.map((m) => ({
    module_key: m.key,
    can_read: false,
    can_create: false,
    can_update: false,
    can_delete: false,
    scope: "own",
    can_reassign: false,
    can_export: false,
    can_view_debt: false,
    can_view_discount: false,
    can_approve: false,
    can_manage_status: false,
    can_reset_password: false,
    can_lock: false,
    can_revoke_sessions: false,
    can_assign_role: false,
    can_transfer: false,
    can_set_head: false,
    can_requote: false,
    can_manage_price: false,
    can_cancel: false,
    can_manage_permissions: false,
    can_clone: false,
    can_toggle_active: false,
    can_reparent: false,
    can_view_salary: false,
    can_adjust: false,
    can_approve_exception: false,
    can_set_credit_terms: false,
    can_record_deposit: false,
    can_assign_work: false,
    can_record_output: false,
    can_handover: false,
    can_request: false,
    can_view_stock: false,
    can_view_cost: false,
    can_set_threshold: false,
    can_post: false,
  }));
}

/** Một module có "quyền" nào không (để đếm N/M ở đầu nhóm + quyết định nhóm nào mở sẵn). */
function rowHasAny(row: PermissionRow): boolean {
  if (row.can_read || WRITE_ACTIONS.some((k) => row[k])) return true;
  const fine = FINE_ACTIONS[row.module_key];
  return fine ? fine.some((a) => row[a.key]) : false;
}

interface PermissionMatrixProps {
  modules: ModuleDef[];
  matrix: PermissionRow[];
  onToggle: (moduleKey: string, action: ActionKey, value: boolean) => void;
  onScope: (moduleKey: string, scope: Scope) => void;
  /** Chế độ chỉ xem: mọi công tắc + phạm vi bị khóa (người dùng thiếu quyền sửa vai trò). */
  readOnly?: boolean;
}

export function PermissionMatrix({
  modules,
  matrix,
  onToggle,
  onScope,
  readOnly = false,
}: PermissionMatrixProps) {
  const moduleLabel = new Map(modules.map((m) => [m.key, m.label]));
  const byKey = new Map(matrix.map((r) => [r.module_key, r]));
  // Nhóm mở/đóng: mặc định mở khi nhóm CÓ quyền; override khi người dùng bấm.
  const [groupOverride, setGroupOverride] = useState<Map<string, boolean>>(new Map());
  // Panel quyền chi tiết bung inline theo module.
  const [openFine, setOpenFine] = useState<Set<string>>(new Set());

  // Dựng danh sách nhóm hiển thị: nhóm đã map + nhóm "Khác" cho module chưa map.
  const mapped = new Set(MODULE_GROUPS.flatMap((g) => g.modules));
  const orphans = matrix.map((r) => r.module_key).filter((k) => !mapped.has(k));
  const groups = [
    ...MODULE_GROUPS.map((g) => ({
      key: g.key,
      label: g.label,
      rows: g.modules.map((k) => byKey.get(k)).filter((r): r is PermissionRow => !!r),
    })),
    ...(orphans.length
      ? [
          {
            key: "khac",
            label: "Khác",
            rows: orphans.map((k) => byKey.get(k)!).filter(Boolean),
          },
        ]
      : []),
  ].filter((g) => g.rows.length > 0);

  const toggleFine = (moduleKey: string) =>
    setOpenFine((cur) => {
      const next = new Set(cur);
      if (next.has(moduleKey)) next.delete(moduleKey);
      else next.add(moduleKey);
      return next;
    });

  return (
    <div className="rdx-perm">
      {groups.map((g) => {
        const granted = g.rows.filter(rowHasAny).length;
        const open = groupOverride.has(g.key) ? groupOverride.get(g.key)! : granted > 0;
        return (
          <section key={g.key} className={`rdx-perm__group${open ? " is-open" : ""}`}>
            <button
              type="button"
              className="rdx-perm__ghead"
              aria-expanded={open}
              onClick={() =>
                setGroupOverride((m) => new Map(m).set(g.key, !open))
              }
            >
              <Icon name="chevron" size={15} className="rdx-perm__gcaret" />
              <span className="rdx-perm__gname">{g.label}</span>
              <span
                className={`rdx-perm__gcount${granted > 0 ? " is-on" : ""}`}
              >
                {granted}/{g.rows.length} có quyền
              </span>
            </button>

            {open && (
              <div className="rdx-perm__rows" role="group" aria-label={g.label}>
                <div className="rdx-perm__colhead" aria-hidden="true">
                  <span className="rdx-perm__c-mod">Module</span>
                  <span className="rdx-perm__c-act">
                    Xem
                    <span className="rdx-perm__fine-hint" title={COL_HINTS.read}>
                      <Icon name="help" size={13} />
                    </span>
                  </span>
                  <span className="rdx-perm__c-act">
                    Thao tác
                    <span className="rdx-perm__fine-hint" title={COL_HINTS.write}>
                      <Icon name="help" size={13} />
                    </span>
                  </span>
                  <span className="rdx-perm__c-scope">
                    Phạm vi
                    <span className="rdx-perm__fine-hint" title={COL_HINTS.scope}>
                      <Icon name="help" size={13} />
                    </span>
                  </span>
                </div>
                {g.rows.map((row) => {
                  const label = moduleLabel.get(row.module_key) ?? row.module_key;
                  const canWrite = WRITE_ACTIONS.every((k) => row[k]);
                  const isNoiQuy = row.module_key === "noi_quy";
                  const fineActs = FINE_ACTIONS[row.module_key];
                  // Công tắc gộp (`keys`): bật = TẤT CẢ cột bật.
                  const fineOn = (a: { key: ActionKey; keys?: ActionKey[] }) =>
                    a.keys ? a.keys.every((k) => row[k]) : !!row[a.key];
                  const fineGranted = fineActs ? fineActs.filter(fineOn).length : 0;
                  const fineIsOpen = openFine.has(row.module_key);
                  return (
                    <div key={row.module_key} className="rdx-perm__row">
                      <div className="rdx-perm__cell rdx-perm__cell--mod">
                        <span className="rdx-perm__mod">
                          {label}
                          {MODULE_HINTS[row.module_key] && (
                            <span
                              className="rdx-perm__fine-hint"
                              title={MODULE_HINTS[row.module_key]}
                              aria-hidden="true"
                            >
                              <Icon name="help" size={13} />
                            </span>
                          )}
                        </span>
                        {fineActs && (
                          <button
                            type="button"
                            className={`rdx-perm__finechip${fineGranted > 0 ? " is-on" : ""}${fineIsOpen ? " is-open" : ""}`}
                            aria-expanded={fineIsOpen}
                            onClick={() => toggleFine(row.module_key)}
                          >
                            {fineGranted}/{fineActs.length} chi tiết
                            <Icon name="chevron" size={12} className="rdx-perm__finecaret" />
                          </button>
                        )}
                      </div>
                      <div className="rdx-perm__cell rdx-perm__cell--act">
                        {isNoiQuy ? (
                          <span className="rdx-perm__always-read">Mọi nhân viên</span>
                        ) : (
                          <input
                            type="checkbox"
                            className="switch"
                            checked={row.can_read}
                            disabled={readOnly}
                            aria-label={`Xem — ${label}`}
                            onChange={(e) =>
                              onToggle(row.module_key, "can_read", e.target.checked)
                            }
                          />
                        )}
                      </div>
                      <div className="rdx-perm__cell rdx-perm__cell--act">
                        {isNoiQuy ? (
                          <span className="rdx-perm__record-actions">
                            <label title="Được tải tài liệu nội quy lên">
                              <input
                                type="checkbox"
                                checked={row.can_create}
                                disabled={readOnly}
                                onChange={(e) => onToggle(row.module_key, "can_create", e.target.checked)}
                              />
                              Thêm
                            </label>
                            <label title="Được xóa tài liệu nội quy">
                              <input
                                type="checkbox"
                                checked={row.can_delete}
                                disabled={readOnly}
                                onChange={(e) => onToggle(row.module_key, "can_delete", e.target.checked)}
                              />
                              Xóa
                            </label>
                          </span>
                        ) : (
                          <input
                            type="checkbox"
                            className="switch"
                            checked={canWrite}
                            disabled={readOnly}
                            aria-label={`Chỉnh sửa (thêm, sửa, xóa) — ${label}`}
                            onChange={(e) =>
                              WRITE_ACTIONS.forEach((k) =>
                                onToggle(row.module_key, k, e.target.checked),
                              )
                            }
                          />
                        )}
                      </div>
                      <div className="rdx-perm__cell rdx-perm__cell--scope">
                        <select
                          className="rdx-perm__scope"
                          value={row.scope}
                          disabled={readOnly}
                          aria-label={`Phạm vi — ${label}`}
                          onChange={(e) =>
                            onScope(row.module_key, e.target.value as Scope)
                          }
                        >
                          {SCOPES.map((s) => (
                            <option key={s.value} value={s.value}>
                              {s.label}
                            </option>
                          ))}
                        </select>
                      </div>

                      {fineActs && fineIsOpen && (
                        <div className="rdx-perm__fine" role="group" aria-label={`Quyền chi tiết — ${label}`}>
                          {fineActs.map((a) => (
                            <label key={a.key} className="rdx-perm__fine-item">
                              <input
                                type="checkbox"
                                className="switch"
                                checked={fineOn(a)}
                                disabled={readOnly}
                                aria-label={`${a.label} — ${label}`}
                                onChange={(e) =>
                                  // Công tắc gộp → set TẤT CẢ cột trong `keys`; thường → 1 cột.
                                  (a.keys ?? [a.key]).forEach((k) =>
                                    onToggle(row.module_key, k, e.target.checked),
                                  )
                                }
                              />
                              <span className="rdx-perm__fine-text">
                                {a.label}
                                {a.hint && (
                                  <span
                                    className="rdx-perm__fine-hint"
                                    title={a.hint}
                                    aria-hidden="true"
                                  >
                                    <Icon name="help" size={13} />
                                  </span>
                                )}
                              </span>
                            </label>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
