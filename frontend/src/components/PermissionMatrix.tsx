// Permission matrix — modules × (Xem / Chỉnh sửa / Phạm vi) + quyền chi tiết. Presentational +
// controlled: the parent owns the rows and gets toggle/scope callbacks. Shared by the Roles
// screen and the per-department "Vai trò & Quyền" panel so both edit permissions identically.
//
// Trình bày (redesign): gom module theo PHÂN HỆ (accordion thu gọn được); mỗi module là một
// hàng với công tắc Xem / Chỉnh sửa / pill Phạm vi; module có quyền chi tiết hiện chip "N/M chi
// tiết" → bấm BUNG INLINE ngay dưới hàng (không popover portal). Data contract KHÔNG đổi.
import { useState } from "react";
import type { ModuleDef, PermissionRow, Scope, RoleTemplate } from "../api/client";
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
  | "can_edit_salary"
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
  | "can_view_log"
  | "can_set_threshold"
  | "can_post"
  | "can_close_book"
  // cham_cong (mg 0194) — một ô = một tab.
  | "can_view_timesheet"
  | "can_approve_late_early"
  | "can_manage_locations"
  | "can_manage_shifts"
  | "can_manage_calendar"
  | "can_view_payroll_table"
  | "can_manage_salary_profiles"
  | "can_manage_piece_rates"
  | "can_manage_leave_types"
  | "can_plan"
  | "can_view_drivers";

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
    // "Xuất file" (can_export) + "Xem công nợ" (can_view_debt) đã gỡ khỏi ma trận 24/08/2026:
    // chốt là 2 tính năng này MẶC ĐỊNH BẬT cho mọi vai có Xem khách — không còn công tắc riêng.
    // Cột DB + ActionKey giữ nguyên (đảo được: thêm lại entry ở đây là bật lại toggle).
    {
      key: "can_set_credit_terms",
      label: "Thiết lập chính sách tài chính",
      hint: 'Sửa chính sách tài chính khách: hạn mức công nợ + số ngày công nợ tối đa (từ ngày xuất HĐ) + rào chiết khấu/markup min–max. Ai cũng XEM, chỉ cờ này mới SỬA. Đây là rào mà "Duyệt báo giá đặc thù" dùng để chặn báo giá vượt ngưỡng.',
    },
  ],
  // Báo giá: thao tác vòng đời THƯỜNG (gửi khách · ghi nhận Khách đồng ý/từ chối · hủy · PDF · tạo bản mới)
  // KHÔNG tách quyền chi tiết — ai có "Sửa" báo giá đều làm được (chủ đầu tư chốt P8). Quyền chi tiết DUY NHẤT
  // còn lại = DUYỆT BÁO GIÁ ĐẶC THÙ (biên thấp / giá trị cao): chỉ vai bật cờ này mới duyệt được đơn trình lên.
  bao_gia: [
    {
      key: "can_approve_exception",
      label: "Duyệt báo giá đặc thù",
      hint: 'Duyệt / từ chối báo giá "đặc thù" — báo giá markup thấp hoặc vượt rào chiết khấu/markup (đặt ở chính sách tài chính khách) mà sale trình lên; duyệt xong mới gửi khách được. Loại thường thì ai Sửa được báo giá đều làm; riêng loại đặc thù cần cờ này. Thường chỉ TP/GĐ Kinh doanh.',
    },
  ],
  // Đơn hàng bán: duyệt đơn đặc thù (nhập tay/bổ sung) + hủy đơn đã chốt = 1 cờ; ghi cọc = Kế toán.
  don_hang_ban: [
    // "Duyệt đơn đặc thù · hủy đơn đã chốt" (can_approve_exception) đã gỡ khỏi ma trận 24/08/2026:
    // luồng duyệt đơn đặc thù vốn đã bỏ, nay chốt hủy-đơn-đã-chốt MẶC ĐỊNH BẬT cho vai có Sửa đơn.
    // Cột DB + ActionKey giữ nguyên (đảo được: thêm lại entry ở đây là bật lại toggle).
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
  // ⚠️ THÊM 17/08/2026 cùng lúc tách khoá. Hai bit này CÓ THẬT ở máy chủ từ lâu
  // (`routers/xep_lich_2.py` gác các endpoint phát hành bằng `approve` + duyệt ngoại lệ bằng
  // `approve_exception`) nhưng hồi đó chúng treo trên khoá `san_xuat`, mà ma trận KHÔNG bày ô nào
  // để cấp ⇒ ngoài admin không ai phát hành được lịch. Cùng bệnh `nghi_phep:approve` hồi 11/08/2026.
  // Khoá mang hậu tố `_2` nhưng đây là màn Xếp lịch DUY NHẤT từ 19/08/2026 — bản cũ gỡ, mg 0219 chép quyền.
  xep_lich_2: [
    {
      key: "can_approve",
      label: "Phát hành lịch ⚠️",
      hint: "Chốt lịch đã xếp thành lịch CHÍNH THỨC cho xưởng chạy (và gỡ phát hành). Phát hành xong là routing bị khoá, tổ nhìn theo lịch này mà làm — nên tách khỏi ô Thao tác: người kéo-thả thử nghiệm không đương nhiên là người chốt.",
    },
    {
      key: "can_approve_exception",
      label: "Duyệt ngoại lệ khi phát hành ⚠️",
      hint: "Phát hành lịch DÙ danh sách Vấn đề còn cảnh báo (trùng máy, nguy cơ trễ hạn, thiếu dữ liệu…). Nặng hơn ô Phát hành: đây là bỏ qua đèn đỏ, phải là người chịu trách nhiệm nếu trễ đơn. Thường chỉ trưởng điều độ.",
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
  // Kho: các ô chi tiết + công tắc chung Xem (can_read) + Lập phiếu (= TẠO + GHI SỔ + HỦY, can_create).
  //   · Tạo yêu cầu (can_request) — người XIN nhập/lĩnh vật tư.
  //   · Xem tồn kho (can_view_stock + can_set_threshold): xem số tồn + khai ngưỡng — KHÔNG kèm giá.
  //   · Xem giá vốn (can_view_cost) — Ô RIÊNG (tách 29/08/2026): CHỈ kế toán thấy đơn giá/giá vốn.
  //     Trước đây gộp chung vào "Xem tất cả kho" nên thủ kho cũng thấy giá; nay tách để chỉ kế toán
  //     xem giá. LƯU Ý: role cũ đã bật ô gộp thì `can_view_cost` vẫn = true trong DB — muốn thủ kho
  //     hết thấy giá phải VÀO BỎ TICK ô "Xem giá vốn" cho role đó.
  // ĐÃ GỘP (bỏ SoD): "Ghi sổ" + "Hủy" nhập chung vào "Lập phiếu" — KHÔNG còn công tắc Ghi sổ riêng.
  // Ai có Lập phiếu là tạo + ghi sổ + hủy được. KHÔNG có Duyệt: ĐÃ BỎ BƯỚC DUYỆT yêu cầu kho
  // (chủ 06/08/2026) — tạo yêu cầu là 'approved' luôn, không ai duyệt nữa (cột `can_approve` giữ
  // trong DB vì dùng chung HR/nơi khác, chỉ gỡ mục "Duyệt yêu cầu" của KHO khỏi UI).
  kho: [
    {
      key: "can_request",
      label: "Tạo yêu cầu nhập/xuất",
      hint: "Lập YÊU CẦU nhập/xuất kho (tổ SX xin lĩnh vật tư, mua hàng xin nhập bổ sung). Người yêu cầu nên để phạm vi \"Của tôi\".",
    },
    {
      key: "can_view_stock",
      keys: ["can_view_stock", "can_set_threshold"],
      label: "Xem tồn kho",
      hint: "XEM số tồn từng kho + KHAI ngưỡng tồn (đèn cảnh báo). KHÔNG kèm giá — muốn thấy đơn giá/giá vốn phải bật thêm ô \"Xem giá vốn\". Thủ kho / ai làm kho bật ô này.",
    },
    {
      key: "can_view_cost",
      label: "Xem giá thành",
      hint: "Thấy ĐƠN GIÁ · THÀNH TIỀN · ở mọi bước kho (yêu cầu · phiếu nhập/xuất · tồn · lô · báo cáo). CHỈ kế toán kho bật — thủ kho thường KHÔNG có ô này. Ẩn ở cả máy chủ, không chỉ ẩn giao diện.",
    },
    {
      key: "can_close_book",
      label: "Báo cáo kho + khóa kỳ (kế toán)",
      hint: "Mở màn \"Báo cáo kho\": sổ nhập-xuất, Nhập-Xuất-Tồn, tính giá kỳ, xuất Excel theo mẫu MISA, và KHÓA KỲ (chốt sổ) toàn kho / từng kho. Chỉ kế toán kho.",
    },
  ],
  // DANH MỤC: đa số KHÔNG có quyền chi tiết — mỗi màn chỉ Xem + Thao tác.
  // (Trước đây bày 5 ô `manage_price` / `clone` / `toggle_active` nhưng KHÔNG endpoint nào kiểm
  //  → tick vào không đổi gì, mà người cấp quyền lại tưởng đã siết được việc sửa giá.)
  // `can_clone` nối THẬT 26/08/2026 (`POST /{id}/clone`, xem `routers/catalog_base.py`) cho 5 màn
  // Giấy · Vật tư khác · Máy thiết bị · Công đoạn · Đầu việc khoán — nên RIÊNG 5 khoá này bày ô
  // "Nhân bản". Không gộp vào `can_create`: vai được TẠO MỚI (gõ tay) chưa chắc nên NHÂN BẢN hàng
  // cũ (nhân đôi cả giá/công thức đang chạy mà không soát lại từng ô).
  dm_giay: [{ key: "can_clone", label: "Nhân bản" }],
  dm_vat_tu: [{ key: "can_clone", label: "Nhân bản" }],
  dm_thiet_bi: [{ key: "can_clone", label: "Nhân bản" }],
  dm_cong_doan: [{ key: "can_clone", label: "Nhân bản" }],
  dm_cong_viec_khoan: [{ key: "can_clone", label: "Nhân bản" }],
  nhan_su: [
    { key: "can_view_salary", label: "Xem lương & BHXH (dữ liệu nhạy cảm)" },
    {
      key: "can_edit_salary",
      label: "Sửa lương & BHXH",
      hint: "Cho nhập/sửa các trường lương, bảo hiểm, thuế trên hồ sơ nhân sự và lúc tạo hồ sơ mới. Quyền này luôn phải đi cùng quyền xem lương.",
    },
    { key: "can_manage_status", label: "Thao tác vòng đời (chính thức/nghỉ/đình chỉ)" },
    { key: "can_transfer", label: "Điều chuyển & nâng bậc" },
    { key: "can_approve", label: "Duyệt yêu cầu cập nhật" },
    { key: "can_export", label: "Xuất Excel danh sách" },
  ],
  // Màn CHẤM CÔNG tách khoá riêng 10/08/2026. Cột Xem = Bảng công tháng + Nhật ký chấm công;
  // cột Chỉnh sửa = ô "Cấu hình chấm công" (Điểm chấm công · Khai ca · Lịch & Ngày lễ). Ba ô
  // dưới đây là các việc phải tách hẳn ra.
  // MỘT Ô = MỘT TAB (chủ chốt 15/08/2026). Cột Xem = mở màn + BA TAB CỦA TÔI (bấm giờ · lịch công
  // của mình · tự xin đi muộn) — đó là việc của chính người đó, không phải quyền được ban.
  // Mỗi ô dưới đây mở đúng MỘT tab, và tab đó luôn dính tới NGƯỜI KHÁC hoặc DÙNG CHUNG.
  cham_cong: [
    {
      key: "can_view_timesheet",
      label: "Bảng công tháng",
      hint: "Lưới người × ngày của cả phạm vi, và là chỗ đặt nút Chốt kỳ công. Đây là công cụ QUẢN LÝ, cùng hạng với Bảng lương — thợ vẫn mở được màn Chấm công để bấm giờ và xem lịch công của mình, nhưng không thấy công của cả xưởng. Trước 15/08/2026 nó đi chung với ô Xem nên cấp Xem là thấy hết.",
    },
    {
      key: "can_approve_late_early",
      label: "Duyệt phiếu đi muộn / về sớm / nghỉ nửa buổi",
      hint: "Mở tab con Duyệt phiếu, cho duyệt / từ chối phiếu của NGƯỜI KHÁC (và khai hộ — khai hộ là duyệt luôn). KHÔNG cần ô này để tự xin phiếu cho mình. Gộp về đây từ khoá 'Đi muộn / về sớm' cũ: nó vốn là một tab của màn này chứ không phải một màn riêng.",
    },
    {
      key: "can_manage_locations",
      label: "Điểm chấm công",
      hint: "Mở tab Điểm chấm công — khai toạ độ và bán kính các điểm được phép chấm. Trước đây ba tab cấu hình đi chung MỘT ô nên bật một cái là mở cả ba.",
    },
    { key: "can_manage_shifts", label: "Khai ca",
      hint: "Mở tab Khai ca — danh mục ca làm việc (giờ vào/ra, ca đêm, tiền cơm/phụ cấp theo ca). Đây là dữ liệu dùng chung cho cả nhà máy." },
    { key: "can_manage_calendar", label: "Lịch & Ngày lễ",
      hint: "Mở tab Lịch & Ngày lễ — tuần làm việc và ngày nghỉ lễ. Đổi ở đây là đổi CÔNG CHUẨN của tháng, tức đổi đơn giá ngày của mọi người." },
    {
      key: "can_view_log",
      label: "Xem Nhật ký chấm công",
      hint: "Tab Nhật ký = TỪNG LƯỢT BẤM của từng người kèm giờ và toạ độ. Khác với cột Xem (chỉ mở Bảng công tháng — số công đã tổng hợp). Ai cần xem công để tính lương thì không đương nhiên cần đọc dấu chân từng người.",
    },
    {
      key: "can_adjust",
      label: "Chấm bù / sửa công",
      hint: "Sửa lượt bấm và chấm bù cho người khác, kể cả duyệt / từ chối Yêu cầu chỉnh công. Không có ô này thì chỉ xem được bảng công.",
    },
    {
      key: "can_lock",
      label: "Chốt kỳ công / Mở lại kỳ ⚠️",
      hint: "Một cú bấm chụp ảnh bảng công của TOÀN CÔNG TY thành số liệu chốt — bảng lương khi kỳ đã khoá đọc đúng ảnh chụp đó; 'Mở lại kỳ' thì xoá sạch ảnh chụp. Trước 10/08/2026 ô này đi chung với 'Chấm bù'. Máy chủ còn đòi Phạm vi 'Tất cả': chốt nửa công ty thì bảng lương không biết nửa nào là nửa nào.",
    },
  ],
  // ⚠️ THÊM 11/08/2026 — trước đó phân hệ Nghỉ phép KHÔNG có mục nào ở đây, nên:
  //   • `can_approve` KHÔNG AI BẬT ĐƯỢC ⇒ tab "Duyệt đơn" và "Lịch nghỉ" không bao giờ hiện với
  //     bất kỳ ai ngoài admin. Chủ chốt báo đúng: "không thấy tab duyệt nghỉ phép ở đâu luôn".
  //   • Quản danh mục LOẠI NGHỈ núp dưới cột "Thao tác" trần — bật nó là mở danh mục của cả công
  //     ty mà người cấp quyền không có cách nào biết.
  nghi_phep: [
    {
      key: "can_approve",
      label: "Duyệt đơn nghỉ phép ⚠️",
      hint: "Duyệt / từ chối đơn xin nghỉ của người khác, và mở tab “Lịch nghỉ” của cả phòng. Kết hợp Phạm vi: “Cả phòng” = tổ trưởng chỉ duyệt người trong tổ mình + các tổ con; “Tất cả” = HCNS duyệt toàn công ty. KHÔNG cần ô này để nhân viên tự gửi/hủy đơn của chính mình.",
    },
    {
      // CỘT RIÊNG từ 15/08/2026 (mg 0197). Trước đó ô này mượn `can_update` — mà `can_update` là
      // một trong ba cột nút "Thao tác" bật cùng lúc, nên bật Thao tác là ô này TỰ SÁNG THEO.
      key: "can_manage_leave_types",
      label: "Quản danh mục loại nghỉ",
      hint: "Thêm / sửa / XOÁ các loại nghỉ (phép năm, nghỉ ốm, không lương…) — chính sách dùng chung cho CẢ CÔNG TY, không phải việc của một phòng. Đây chính là ý nghĩa của cột “Thao tác” ở dòng này; cột “Xoá” không dùng tới.",
    },
  ],
  // Giao hàng (19/08/2026) — MỘT Ô = MỘT TAB, cùng luật với Chấm công và Lương.
  giao_hang: [
    {
      key: "can_plan",
      label: "Lên đơn giao hàng",
      hint: "Mở tab “Yêu cầu giao” + nút Lên đơn giao hàng (chọn tài xế, giờ lấy, giờ dự kiến giao) + nút Gửi đề nghị xuất hàng sang kho. Tách khỏi cột Thao tác vì gửi yêu cầu giao (Bán hàng làm) và xếp chuyến cho tài xế (Quản lý Giao hàng làm) là việc của hai người — gộp một cột là Bán hàng xếp được lịch tài xế.",
    },
    {
      key: "can_cancel",
      label: "Huỷ yêu cầu / huỷ chuyến",
      hint: "Huỷ một yêu cầu giao chưa lên kế hoạch, hoặc huỷ chuyến đã xếp (phải nhập lý do, phiếu ở lại có vết). Tách khỏi cột Thao tác vì tài xế ở phạm vi “Của tôi” vẫn phải nhập được kết quả chuyến, nhưng bỏ chuyến là quyết định của điều phối.",
    },
    {
      key: "can_view_drivers",
      label: "Nhân viên giao hàng",
      hint: "Mở tab “Nhân viên giao hàng” — lịch làm việc, chuyến đang chạy, số chuyến hoàn thành và tổng km trong ngày của NGƯỜI KHÁC. Ô riêng vì tài xế ở phạm vi “Của tôi” không được thấy năng suất đồng nghiệp.",
    },
  ],
  // Tách khỏi ô "Chấm bù" của màn Chấm công ngày 11/08/2026.
  tang_ca: [
    {
      key: "can_approve",
      label: "Duyệt phiếu tăng ca",
      hint: "Duyệt / từ chối phiếu tăng ca của người khác (và tạo hộ cho thợ — tạo hộ là duyệt luôn). Kết hợp Phạm vi: 'Cả phòng' = tổ trưởng chỉ đụng được người trong tổ mình + các tổ con; 'Tất cả' = HCNS duyệt toàn công ty. KHÔNG cần cờ này để nhân viên tự gửi/hủy phiếu của chính mình.",
    },
  ],
  luong: [
    { key: "can_manage_salary_profiles", label: "Lương nhân viên",
      hint: "Mở tab Lương nhân viên — khai và điều chỉnh mức lương từng người (lương vị trí, trách nhiệm, bảo hiểm). Trước 15/08/2026 tab này đi theo cột Thao tác, nên bật Thao tác là ba tab bung ra cùng lúc." },
    { key: "can_manage_piece_rates", label: "Lương khoán",
      hint: "Mở tab Lương khoán — đơn giá khoán theo tổ / công việc. Dữ liệu dùng chung, không phải của một người." },
    {
      key: "can_view_payroll_table",
      label: "Bảng lương tháng",
      hint: "Danh sách lương của cả phạm vi, kèm nút Tính lại · Chốt kỳ · Đánh dấu đã chi. Đây là công cụ QUẢN LÝ — nhân viên xem phiếu lương của chính mình ở tab riêng, không cần ô này. Trước 15/08/2026 nó đi theo cột Xem, nên cấp ô Lương ở phạm vi 'Của tôi' là thợ vẫn mở được bảng lương cả công ty.",
    },
    {
      key: "can_lock",
      label: "Chốt bảng lương / Mở lại kỳ ⚠️",
      hint: "Chốt kỳ lương của TOÀN CÔNG TY (kỳ lương là một bản ghi chung, không chốt riêng từng tổ được) và mở lại kỳ đã chốt. Máy chủ còn đòi Phạm vi “Tất cả”.",
    },
    {
      key: "can_manage_status",
      label: "Đánh dấu đã chi lương ⚠️",
      hint: "Tuyên bố TIỀN ĐÃ RA tới tay người lao động — và khoá kỳ luôn (muốn mở lại phải huỷ đã chi trước). Tách khỏi ô Chốt từ 10/08/2026: người tính lương chốt số, kế toán mới xác nhận đã trả. Máy chủ còn đòi Phạm vi “Tất cả”.",
    },
    {
      key: "can_view_salary",
      label: "Xem cấu hình lương",
      hint: "Cho xem thang bậc, khung lương, KPI, phụ cấp, bảo hiểm và lịch sử lương nhân viên. Không cần cấp quyền này để nhân viên xem Phiếu lương của tôi.",
    },
    { key: "can_approve", label: "Duyệt tạm ứng" },
    { key: "can_export", label: "Xuất bảng lương / file chuyển khoản" },
  ],
  thu_mua: [
    // ĐÃ BỎ 12/08/2026 (chủ chốt test rồi quyết) — hai ô này không đáng tồn tại:
    //   • "Sửa / đảo trạng thái đơn sau khi nhận hàng" (`can_manage_status`): ba việc nó gác
    //     (sửa số nhận · mở lại đơn · đóng đơn) là việc thường ngày của chính người lập phiếu,
    //     nay gộp vào ô "Thao tác". Migration `0191` đổ quyền cũ về `can_update`.
    //   • "Hủy PMH" (`can_cancel`): CHƯA BAO GIỜ được đọc. `purchase_service.cancel` gác bằng
    //     `ke_toan:approve` (hoặc chính người lập, khi phiếu còn nháp) — ô này bật hay tắt đều
    //     không đổi gì. Đã khai vào `deps.O_CHET_DA_XAC_MINH`.
  ],
  // Ô của màn Đơn mua hàng (Kế toán) — dời từ phân hệ Mua hàng xuống 11/08/2026: nút Duyệt /
  // Từ chối chỉ có ở màn này, để ô trên kia thì nhìn ma trận không đoán ra nó tác dụng ở đâu.
  ke_toan: [
    {
      key: "can_approve",
      label: "Duyệt / từ chối PMH ⚠️",
      hint: "Duyệt hoặc từ chối phiếu mua hàng — quyết định phiếu có đi tiếp thành khoản chi hay không. Nút nằm ngay màn này. Tách vai vẫn giữ: LẬP phiếu chi là ô riêng bên màn Phiếu chi, nên có ô này mà không có ô kia thì duyệt xong vẫn không tự viết được phiếu chi.",
    },
  ],
  // Phân hệ Kế toán tách mỗi màn một khoá (10/08/2026). Ô "Lập phiếu" nay là cột **Thêm** của
  // chính màn đó, không còn núp dưới tên `can_approve` — nên ở đây chỉ còn các quyền phụ.
  phieu_chi: [
    { key: "can_cancel", label: "Hủy phiếu chi" },
    { key: "can_export", label: "In / xuất phiếu chi" },
  ],
  // Ô "Xác nhận đã thu tiền" (`can_manage_status`) ĐÃ GỠ 27/08/2026: phiếu thu nay lập ra là ĐÃ
  // THU, không còn trạng thái chờ nên không còn gì để xác nhận. Khoá quyền vẫn tồn tại ở server
  // (`mark-received`) cho phiếu CŨ lỡ nằm lại ở trạng thái chờ, nhưng không bày thành ô bật/tắt
  // nữa — bày một ô cho cái nút không bao giờ hiện chỉ tổ làm người cấp quyền đoán mò.
  phieu_thu: [
    { key: "can_cancel", label: "Hủy phiếu thu" },
    { key: "can_export", label: "In / xuất phiếu thu" },
  ],
};

// Giải thích NGẮN cho từng module: bật "Xem" / "Chỉnh sửa" thì người dùng làm được gì. Hiện qua
// dấu ⓘ cạnh tên module (cùng khuôn tooltip với quyền chi tiết). Module không khai ở đây thì
// không hiện ⓘ — thà thiếu còn hơn mô tả sai.
const MODULE_HINTS: Record<string, string> = {
  self_service:
    "Việc người lao động làm với hồ sơ CỦA CHÍNH MÌNH: tự chấm công, xem công và phiếu lương của mình, tự gửi đơn nghỉ / phiếu tăng ca / xin tạm ứng. Vai mới sinh ra đã bật sẵn ô này. Tắt đi thì người đó không tự chấm công được nữa — cân nhắc trước khi bỏ tick.",
  giao_hang:
    "Xem: mở màn Giao hàng — tab “Đơn giao hàng”, lọc theo Phạm vi. Thao tác: gửi yêu cầu giao từ đơn hàng bán, bấm đã lấy hàng, nhập kết quả + số km. Lên đơn giao hàng và tab Nhân viên giao hàng là hai ô riêng bên dưới. Kho KHÔNG cần ô này — nút Duyệt của kho nằm trong Hộp yêu cầu và đi theo ô Kho.",
  nhan_su:
    "Xem: mở Hồ sơ nhân sự (danh sách NV, chi tiết hồ sơ). Chỉnh sửa: thêm/sửa/xóa hồ sơ. Lương & BHXH của NV là dữ liệu nhạy cảm nên tách riêng thành quyền xem và quyền sửa. Màn Chấm công KHÔNG còn nằm trong ô này — nó có ô riêng ngay bên dưới.",
  cham_cong:
    "Xem: mở màn Chấm công (Bảng công tháng + Nhật ký chấm công) trong phạm vi được cấp. Chỉnh sửa: ba tab cấu hình — Điểm chấm công, Khai ca, Lịch & Ngày lễ (gác cả xem lẫn sửa, vì toạ độ điểm chấm công và lưới phân ca không phải thứ ai cũng cần đọc). Chấm bù và Chốt kỳ nằm ở quyền chi tiết. Nhân viên tự chấm công cho mình thì dùng ô Tự phục vụ, không cần ô này.",
  noi_quy:
    "Xem: đọc danh sách nội quy và mở file. Vai mới sinh ra đã bật sẵn — nội quy lao động thì ai cũng phải đọc. Thêm / xoá tài liệu nằm ở cột Thêm và Xoá.",
  nghi_phep:
    "Xem: thấy đơn nghỉ trong phạm vi được cấp. Chỉnh sửa: quản danh mục loại nghỉ. Nhân viên tự gửi và tự hủy đơn của mình thì KHÔNG cần cấp gì thêm.",
  tang_ca:
    "Xem: thấy mục Tăng ca trên thanh bên + danh sách phiếu trong phạm vi. Nhân viên tự gửi / tự hủy phiếu của chính mình thì KHÔNG cần cấp quyền nào. Muốn DUYỆT phiếu người khác thì bật quyền chi tiết “Duyệt phiếu tăng ca”.",
  di_muon:
    "Xem: thấy danh sách phiếu đi muộn / về sớm / nghỉ nửa buổi trong phạm vi (tab nằm trong màn Chấm công). Nhân viên tự xin / tự hủy phiếu của CHÍNH MÌNH thì KHÔNG cần cấp quyền nào — tab luôn hiện. Muốn DUYỆT phiếu người khác (và khai hộ thợ) thì bật quyền chi tiết “Duyệt phiếu đi muộn / về sớm”.",
  luong:
    "Xem: MỞ MÀN Lương — chỉ thấy hai tab của chính mình (Phiếu lương của tôi, Tạm ứng của tôi). Không có ô này là không vào được màn, kể cả để xem phiếu lương của mình, nên vai nào cũng nên bật. Thao tác: gửi đề nghị tạm ứng / xin lương đợt 1 cho chính mình, và ghi ở những tab đã mở. Bảng lương tháng, Lương nhân viên, Lương khoán, Cấu hình, duyệt tạm ứng, chốt kỳ, xuất file — mỗi thứ một ô ở quyền chi tiết bên dưới.",
  thu_mua:
    "Xem: xem danh sách YCMH và PMH trong phạm vi được cấp. Chỉnh sửa: lập/sửa/gửi duyệt PMH, đánh dấu đã mua/đã nhận. Duyệt-từ chối PMH và hủy PMH nằm ở quyền chi tiết.",
  // Hai chú giải dưới bổ sung 21/08/2026: trước đó hai màn này KHÔNG có dòng nào, người cấp quyền
  // phải tự đoán "Xem cái này thì thấy gì" (xem docs/RBAC_QUYEN_THEO_MODULE.md §5).
  yeu_cau_mua_hang:
    "Xem: mở màn Yêu cầu mua hàng (YCMH của các bộ phận) trong phạm vi được cấp. Màn này CỐ Ý mở cho nhiều nhóm — báo giá, kho, sản xuất, giấy, kế toán, thu mua đều vào được bằng ô Xem của chính họ, nên bật ô này chỉ là MỘT trong bảy đường vào. Chỉnh sửa: lập yêu cầu cho bộ phận mình, sửa khi còn nháp, và hủy yêu cầu. Chuyển YCMH thành phiếu mua hàng là việc của ô Mua hàng.",
  nha_cung_cap:
    "Xem: danh mục Nhà cung cấp + bảng mặt hàng NCC đang bán (kèm tải mẫu và xuất Excel). Chỉnh sửa: thêm/sửa NCC, ngừng dùng, và nhập bảng mặt hàng từ Excel. Ô này còn mở TÀI KHOẢN NGÂN HÀNG của nhà cung cấp ở màn Kế toán — người quản danh mục NCC sửa được TK của họ mà không cần ô Tài khoản ngân hàng.",
  khach_hang:
    "Xem: danh bạ khách + lịch sử giao dịch (kèm xuất file & thẻ công nợ — mặc định bật). Chỉnh sửa: thêm/sửa/xóa khách. Điều chuyển sang sale khác và đặt chính sách tài chính nằm ở quyền chi tiết.",
  bao_gia:
    "Xem: xem báo giá trong phạm vi. Chỉnh sửa: tạo/sửa báo giá + thao tác vòng đời thường (gửi khách, ghi nhận đồng ý/từ chối, hủy, xuất PDF, tạo bản mới). Riêng báo giá “đặc thù” cần quyền chi tiết để duyệt.",
  don_hang_ban:
    "Xem: xem đơn hàng bán. Chỉnh sửa: tạo/sửa đơn (kèm hủy đơn đã chốt — mặc định bật). Ghi phiếu thu cọc nằm ở quyền chi tiết.",
  // 6 dòng dưới đây gác 6 MÀN RIÊNG (tách 17/08/2026). Trước đó `san_xuat` mở 4 màn và
  // `ky_thuat_may` mở 2 — nhãn cũ chỉ kể một màn nên người cấp quyền không đoán ra mình vừa mở gì.
  san_xuat:
    "CHỈ màn Kế hoạch sản xuất (hàng chờ → lệnh SX → routing). Xem: mở hộp việc / lệnh trong phạm vi. Chỉnh sửa: tạo lệnh, sửa routing, đánh dấu sẵn sàng. Gán thợ, ghi sản lượng, bàn giao giữa tổ nằm ở quyền chi tiết. Kế hoạch vật tư · Bài ghép · Xếp lịch là ba ô RIÊNG ngay bên dưới — từ 17/08/2026 ô này không còn mở chúng nữa.",
  ke_hoach_vat_tu:
    "Màn Kế hoạch vật tư (bảng cân đối: lệnh nào thiếu gì, hôm nào phải đặt). Xem: đọc bảng cân đối — trong đó có GIÁ vật tư và giá trị phải mua, nên cân nhắc trước khi cấp rộng. Chỉnh sửa: khai/sửa số giữ chỗ cho lệnh. Nút “Đề nghị mua” của dòng thiếu KHÔNG đi theo ô này mà theo quyền tạo yêu cầu mua hàng.",
  // Khoá vẫn mang hậu tố `_2` (đổi khoá trong DB không đáng), nhưng đây là màn Bài ghép DUY NHẤT
  // từ 18/08/2026 — bản cũ đã gỡ, mg 0216 chép quyền sang.
  bai_ghep_2:
    "Màn Bài ghép (gom công đoạn in của nhiều lệnh chạy chung một tờ). Xem: đọc hàng chờ ghép và các bài đã ghép. Chỉnh sửa: tạo bài, chọn giấy/khổ chung, sửa số con trên tờ, khai hao hụt, đánh dấu sẵn sàng.",
  xep_lich_2:
    "Màn Xếp lịch công đoạn (bảng Gantt theo máy + danh sách Vấn đề). Xem: nhìn lịch cả xưởng. Chỉnh sửa: đưa lệnh vào lịch, gán máy/ca/giờ, kéo-thả dời khe, khóa/gỡ. PHÁT HÀNH lịch và duyệt ngoại lệ nằm ở quyền chi tiết — sửa lịch nháp khác với chốt lịch cho xưởng chạy.",
  ky_thuat_may:
    "CHỈ màn Sửa chữa máy. Xem: xem phiếu + ảnh hiện trạng/chứng thực — hợp với quản đốc, điều độ. Chỉnh sửa: ghi nhận máy hỏng, ghi đã sửa gì, tải ảnh và xác nhận xong — hợp với tổ sửa chữa. Không có quyền duyệt riêng: cửa chặn là ẢNH chứng thực, thiếu ảnh thì KHÔNG AI đóng được phiếu, kể cả giám đốc.",
  phieu_bao_tri:
    "Màn Phiếu bảo trì (bảo dưỡng định kỳ sinh từ lịch của máy). Tách khỏi Sửa chữa máy 17/08/2026: điều độ cần biết máy nào sắp nằm để né khi xếp lịch, mà không cần đọc phiếu máy hỏng. Xem: xem phiếu + lịch đến hạn. Chỉnh sửa: sinh phiếu từ lịch, tick hạng mục, dời lịch, tải ảnh, xác nhận xong. Cửa chặn vẫn là ẢNH.",
  yeu_cau_sua_chua:
    "Cùng màn Sửa chữa máy, nhưng là khung “Yêu cầu báo hỏng” dành cho người NGOÀI tổ kỹ thuật (thợ đứng máy, QC, tổ trưởng). Xem: nhìn hàng chờ báo hỏng — để không hai người cùng báo một cái máy. Chỉnh sửa: gửi lời báo và sửa lại lời báo CỦA CHÍNH MÌNH khi chưa ai tiếp nhận. Ô này KHÔNG cho mở/đóng phiếu sửa chữa; biến lời báo thành phiếu là quyền “Sửa chữa máy”.",
  vai_tro:
    "Xem: xem danh sách vai trò và ma trận quyền. Chỉnh sửa: thêm/sửa/xóa vai trò. Muốn SỬA được chính ma trận này thì cần quyền chi tiết “Sửa ma trận phân quyền”.",
  nguoi_dung:
    "Xem: danh sách tài khoản. Chỉnh sửa: tạo/sửa tài khoản. Đặt lại mật khẩu, khóa tài khoản, thu hồi phiên, gán vai trò, chuyển phòng ban nằm ở quyền chi tiết.",
  phong_ban:
    "Xem: xem cây tổ chức phòng ban / tổ. Chỉnh sửa: thêm/sửa/xóa phòng ban. Đặt trưởng phòng và đổi cấp trên trong cây nằm ở quyền chi tiết.",
  ke_toan:
    "Xem: mở màn Đơn mua hàng của kế toán (danh sách PMH đã duyệt, chờ chi). CHỈ màn này — Phiếu chi, Phiếu thu, Công nợ và Tài khoản ngân hàng là các ô riêng bên dưới.",
  phieu_chi:
    "Xem: mở màn Phiếu chi / UNC. Thêm: LẬP phiếu cọc, phiếu thanh toán và gán chứng từ. Hủy phiếu và in/xuất nằm ở quyền chi tiết.",
  phieu_thu:
    "Xem: mở màn Phiếu thu. Thêm: LẬP phiếu thu và gán chứng từ — phiếu lập ra là ĐÃ THU, sai thì hủy rồi lập lại. Hủy phiếu, in/xuất nằm ở quyền chi tiết.",
  cong_no_phai_tra:
    "Xem: mở màn Công nợ phải trả (số còn nợ từng nhà cung cấp). Số liệu tính ra từ PMH + phiếu chi nên không có gì để sửa ở đây.",
  cong_no_phai_thu:
    "Xem: mở màn Công nợ phải thu (số khách còn nợ). Số liệu chỉ phát sinh từ hóa đơn bán đã ghi nhận, sau đó trừ cọc được cấn và phiếu thu; đơn mới chốt chưa tạo công nợ.",
  tk_ngan_hang:
    "Xem: mở màn Tài khoản ngân hàng (TK công ty + TK nhà cung cấp). Chỉnh sửa: thêm/sửa/ngừng dùng tài khoản. TK của nhà cung cấp thì người quản danh mục Nhà cung cấp cũng sửa được.",
};

// Nghĩa CHUNG của 3 cột — luôn đúng với mọi module, hiện ở dòng tiêu đề.
const COL_HINTS = {
  read: "Cho phép mở và đọc dữ liệu của module này. Nếu tắt “Xem”, hệ thống sẽ tắt luôn các quyền thao tác liên quan để tránh cấp quyền nửa chừng.",
  write: "Gộp 3 quyền Thêm + Sửa + Xóa. Khi bật thao tác, hệ thống tự hiểu người đó cũng phải được xem module này.",
  scope: "Giới hạn được đụng tới bao nhiêu dữ liệu: “Của tôi” = chỉ bản ghi của chính mình · “Cả phòng” = phòng/tổ mình và mọi tổ con · “Tất cả” = toàn công ty.",
};

export const SCOPES: { value: Scope; label: string }[] = [
  { value: "own", label: "Của tôi" },
  { value: "department", label: "Cả phòng" },
  { value: "all", label: "Tất cả" },
];

// Gom module theo PHÂN HỆ để ma trận quyền đọc được (thu gọn từng nhóm). Module không nằm trong
// nhóm nào rơi vào "Khác" (fallback an toàn khi backend thêm module mới chưa map).
// Khoá CŨ đã gộp về nơi khác — ẨN khỏi ma trận, KHÔNG xoá dữ liệu (ĐẢO ĐƯỢC: xoá set này là chúng
// hiện lại y cũ). Đã soi đủ BA nơi (cổng router · `authz.can` ở service · `can(...)` ở giao diện)
// + đếm dữ liệu thật ngày 26/08/2026 — không dòng code nào còn đọc chúng:
//   · `self_service`       — BỎ 15/08/2026. Hằng `MODULE_TU_PHUC_VU` còn khai ở 6 router và
//                            `SELF_SERVICE_MODULE` còn export ở Sidebar, nhưng KHÔNG nơi nào dùng.
//                            20/23 vai đang bật ⇒ ẩn mà KHÔNG ai mất quyền (vì không ai đọc).
//   · `yeu_cau_chinh_cong` — gộp về `cham_cong.approve`. Số khớp: 2 vai ↔ 2 vai.
//   · `di_muon`            — gộp về `cham_cong.approve_late_early`. Số khớp: 3 vai ↔ 3 vai. Việc
//                            CUỐI CÙNG của nó (badge phiếu chờ duyệt + kênh SSE) đã chuyển sang
//                            `cham_cong` cùng ngày; đã đếm: mọi vai có `di_muon` đều đã có
//                            `cham_cong` nên không ai mất badge.
// Xoá HẲN (dòng `role_permissions` + khoá ở `seed.py`/`deps.py` + hằng chết) để LƯỢT SAU — việc đó
// không đảo được nên cần migration + chủ gật.
const MODULE_DA_NGUNG = new Set(["self_service", "di_muon", "yeu_cau_chinh_cong"]);

const MODULE_GROUPS: {
  key: string;
  label: string;
  modules: string[];
  /** Nhóm KHÔNG có cột Phạm vi: dữ liệu dùng chung toàn công ty, không có "của tôi \ cả phòng".
   *  Danh mục là nhóm duy nhất như vậy — `scope` của nó không service nào đọc, để dropdown ở đó
   *  chỉ khiến người cấp quyền tưởng mình vừa giới hạn được cái gì. Backend ép `all` khi lưu. */
  noScope?: boolean;
}[] = [
  {
    key: "kinh_doanh",
    label: "Kinh doanh",
    // `giao_hang` đứng ngay sau `don_hang_ban`: nó là khúc SAU của đơn, và người cấp quyền dò
    // theo màn hình chứ không theo tên kỹ thuật. Thiếu ở đây thì nó rơi vào nhóm "Khác" —
    // vẫn cấp được, nhưng phải cuộn xuống cuối mới thấy.
    modules: ["khach_hang", "bao_gia", "don_hang_ban", "giao_hang", "tinh_gia_thanh"],
  },
  // MỘT MÀN = MỘT DÒNG, xếp đúng thứ tự menu "Sản xuất" để người cấp quyền dò theo màn hình.
  // 6 mục menu → 6 dòng; trước 17/08/2026 chỉ có 2, bật đủ 2/2 vẫn không siết được màn nào.
  // Thiếu một khoá ở đây thì nó rơi vào nhóm "Khác" — mà nhóm "Khác" mặc định THU GỌN khi chưa
  // cấp gì (`open = granted > 0`), nên module mới coi như tàng hình: không cấp được ⇒ menu không
  // hiện ⇒ tưởng module chưa dựng. `bai_ghep_2` dính đúng bẫy đó ngày 18/08/2026.
  {
    key: "san_xuat",
    label: "Sản xuất",
    modules: [
      "san_xuat",
      "ke_hoach_vat_tu",
      "bai_ghep_2",
      "xep_lich_2",
      "ky_thuat_may",
      "yeu_cau_sua_chua",
      "phieu_bao_tri",
    ],
  },
  { key: "kho", label: "Kho", modules: ["kho"] },
  // Thu mua tách khỏi nhóm Kho (10/08/2026): mỗi MÀN một ô quyền + phạm vi riêng, cấp tới đâu
  // làm được tới đó. Thiếu một khoá ở đây thì nó rơi vào nhóm "Khác" — vẫn cấp được, chỉ khó tìm.
  {
    key: "thu_mua",
    label: "Thu mua",
    modules: ["yeu_cau_mua_hang", "thu_mua", "nha_cung_cap"],
  },
  {
    key: "ke_toan",
    label: "Kế toán",
    modules: [
      "ke_toan",
      "phieu_chi",
      "phieu_thu",
      "cong_no_phai_tra",
      "cong_no_phai_thu",
      "tk_ngan_hang",
    ],
  },
  {
    key: "nhan_su",
    label: "Nhân sự",
    // ĐÃ GỠ 15/08/2026: "Đi muộn / về sớm" và "Yêu cầu chỉnh công" — hai TAB của màn Chấm công,
    // không phải hai màn. Quyền của chúng nay là ô chi tiết của chính Chấm công (mg 0194); để lại
    // hai dòng này thì tick cũng không mở thêm gì.
    // Ô "Tự phục vụ" ĐÃ BỎ 15/08/2026: phần "của tôi" là quyền đương nhiên của mọi tài khoản, nên
    // nó không phải một dòng để cấp. Nó cũng không phải một MÀN — nó cắt ngang bốn màn khác.
    modules: [
      // Phòng ban ĐỨNG TRƯỚC Hồ sơ nhân sự (chủ chốt 11/08/2026): cây tổ chức là cái khung chứa
      // hồ sơ, đọc từ trên xuống mới thuận. Trước đây nó nằm mãi dưới nhóm "Hệ thống".
      "phong_ban",
      "nhan_su",
      "cham_cong",
      "nghi_phep",
      "tang_ca",
      "luong",
      "noi_quy",
    ],
  },
  {
    key: "danh_muc",
    label: "Danh mục",
    // MỘT MÀN = MỘT DÒNG, xếp đúng thứ tự menu "Cấu hình danh mục" để người cấp quyền dò theo
    // màn hình. 11 mục menu → 11 dòng; trước đây chỉ có 5, bật đủ 5/5 vẫn thiếu màn.
    modules: [
      "dm_loai_san_pham",
      "dm_thiet_bi",
      "dm_cong_doan",
      // Công việc khoán (17/08/2026): tách khỏi ô quyền `luong`. Nay cấp được "khai đơn giá khoán"
      // mà không phải mở cả bảng lương cho người ta.
      "dm_cong_viec_khoan",
      "dm_bu_hao",
      "dm_don_vi",
      "dm_chung_loai_giay",
      "dm_giay",
      "dm_vat_tu",
      "dm_thanh_pham",
      "khuon_be",
      "dm_kho_hang",
    ],
    noScope: true,
  },
  {
    key: "he_thong",
    label: "Hệ thống",
    // `phong_ban` đã dời sang nhóm Nhân sự (11/08/2026) — nó là cây tổ chức nhân sự, không phải
    // cấu hình hệ thống.
    modules: ["dashboard", "vai_tro", "nguoi_dung", "activity_log"],
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
    can_edit_salary: false,
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
    can_view_log: false,
    can_set_threshold: false,
    can_post: false,
    can_close_book: false,
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
  /** Bảng VAI MẪU (đợt 6). Bỏ trống ⇒ không hiện thanh chọn mẫu. */
  templates?: RoleTemplate[];
  /** Người dùng chọn một mẫu — cha THAY SẠCH ma trận bằng `template.permissions`. */
  onApplyTemplate?: (template: RoleTemplate) => void;
}

//: Phạm vi nào có nghĩa ở màn nào. Màn không khai ở đây thì cho chọn cả ba như cũ.
//
//  Vì sao khoá: bày ra một lựa chọn không có tác dụng là nói dối người cấp quyền. "Nhà cung cấp"
//  là danh mục dùng chung — không có khái niệm NCC "của tôi"; "Đơn mua hàng (Kế toán)" là hộp thư
//  của cả công ty; "Tự phục vụ" thì đúng nghĩa chỉ của mình; duyệt yêu cầu chỉnh công của CHÍNH
//  MÌNH thì vô nghĩa nên bỏ "Của tôi".
//
//  ⚠️ Lương CỐ Ý chưa khai ở đây — khoá nó về "Tất cả" là MỞ RỘNG dữ liệu lương ra toàn công ty,
//  chờ chủ chốt chốt (xem PRD vòng 2 §2.6).
const PHAM_VI_CHO_PHEP: Record<string, Scope[]> = {
  nha_cung_cap: ["all"],
  ke_toan: ["all"],
  cong_no_phai_tra: ["all"],
  cong_no_phai_thu: ["all"],
  nhan_su: ["department", "all"],
  yeu_cau_chinh_cong: ["department", "all"],
  // Kỹ thuật máy nằm trong `SCOPELESS_MODULES` của máy chủ (ép `all` lúc lưu) NHƯNG ở nhóm Sản
  // xuất — nhóm này có cột Phạm vi thật (`san_xuat` dùng), nên không bỏ ô đi được như nhóm Danh
  // mục. Khoá về một lựa chọn để ô hiện mờ thay vì bày ba lựa chọn mà chọn gì cũng ra `all`.
  ky_thuat_may: ["all"],
  // Bốn màn tách khỏi khối Sản xuất 17/08/2026 cũng nằm trong `SCOPELESS_MODULES` của máy chủ
  // (ép `all` lúc lưu) nhưng ở nhóm Sản xuất — nhóm này có cột Phạm vi thật vì `san_xuat` dùng
  // (`lsx.py` lọc lệnh theo scope), nên không bỏ cột đi được. Khoá về một lựa chọn để ô hiện mờ.
  ke_hoach_vat_tu: ["all"],
  bai_ghep_2: ["all"],
  xep_lich_2: ["all"],
  phieu_bao_tri: ["all"],
  // Không có “chỉ của tôi”: ai cũng phải THẤY hết yêu cầu đang chờ thì mới thôi báo trùng. Việc
  // “chỉ sửa lời báo của mình” backend chặn bằng người gửi, không bằng phạm vi.
  yeu_cau_sua_chua: ["all"],
};

//: Ô CHỈ BẬT ĐƯỢC khi phạm vi là "Tất cả" (chủ chốt 15/08/2026).
//: Ba tab cấu hình dưới đây ghi vào dữ liệu DÙNG CHUNG cả nhà máy — đổi lịch lễ hay khai ca là
//: đổi CÔNG của toàn bộ nhân viên, không phải của một tổ. Máy chủ cũng chặn (403), nên không khai
//: ở đây thì người cấp quyền tick được mà người dùng bấm vào ăn lỗi.
const O_DOI_PHAM_VI_TOAN_CTY: ReadonlySet<string> = new Set([
  "can_manage_locations",
  "can_manage_shifts",
  "can_manage_calendar",
  // Chốt kỳ công / Mở lại kỳ: máy chủ ĐÃ đòi phạm vi "Tất cả" từ đợt trước, nhưng ma trận không
  // nói ra ⇒ tick được rồi bấm mới ăn 403. Một cú bấm đóng băng bảng công của TOÀN CÔNG TY; chốt
  // nửa nhà máy thì bảng lương không biết nửa nào là nửa nào.
  "can_lock",
]);

const CANH_BAO_PHAM_VI =
  "Ô này đụng vào dữ liệu dùng chung của CẢ NHÀ MÁY (điểm chấm công · ca · lịch lễ · chốt kỳ " +
  "công) nên chỉ bật được khi Phạm vi là “Tất cả”. Đổi Phạm vi sang “Tất cả” rồi bật lại.";

const CANH_BAO_O_CHET =
  "Ô này chưa nối vào chức năng nào — bật cũng không mở thêm gì.";

export function PermissionMatrix({
  modules,
  matrix,
  onToggle,
  onScope,
  readOnly = false,
  templates,
  onApplyTemplate,
}: PermissionMatrixProps) {
  const moduleLabel = new Map(modules.map((m) => [m.key, m.label]));
  // Máy chủ khai những ô ĐÃ XÁC MINH là chết (`/api/rbac/modules` → `viec_chet`). Chỉ tắt + khoá
  // đúng mấy ô đó.
  //
  // ⚠️ ĐỪNG đảo lại thành "cái gì máy chủ không gác thì chết". Bản đầu (11/08/2026) làm vậy và
  // khoá nhầm hàng loạt ô đang dùng được — In/xuất phiếu chi · phiếu thu · Đặt trưởng phòng · Đổi
  // cấp trên · Xem lương & BHXH · Sửa lương & BHXH · Thao tác vòng đời · Điều chuyển & nâng bậc.
  // Lý do: rất nhiều ô chỉ thi hành ở GIAO DIỆN (ẩn/hiện nút), máy chủ không hề biết.
  const viecChet = new Map(
    modules.filter((m) => m.viec_chet).map((m) => [m.key, new Set(m.viec_chet!)]),
  );
  /** Mặc định CÒN SỐNG — thà để thừa một ô vô hại còn hơn khoá nhầm một ô đang dùng. */
  const oSong = (moduleKey: string, viec: string): boolean =>
    !viecChet.get(moduleKey)?.has(viec);
  const matrixHienThi = matrix.filter((r) => !MODULE_DA_NGUNG.has(r.module_key));
  const byKey = new Map(matrixHienThi.map((r) => [r.module_key, r]));
  // Nhóm mở/đóng: mặc định mở khi nhóm CÓ quyền; override khi người dùng bấm.
  const [groupOverride, setGroupOverride] = useState<Map<string, boolean>>(new Map());
  // Panel quyền chi tiết bung inline theo module.
  const [openFine, setOpenFine] = useState<Set<string>>(new Set());

  // Dựng danh sách nhóm hiển thị: nhóm đã map + nhóm "Khác" cho module chưa map.
  const mapped = new Set(MODULE_GROUPS.flatMap((g) => g.modules));
  const orphans = matrixHienThi.map((r) => r.module_key).filter((k) => !mapped.has(k));
  const groups = [
    ...MODULE_GROUPS.map((g) => ({
      key: g.key,
      label: g.label,
      noScope: g.noScope === true,
      rows: g.modules.map((k) => byKey.get(k)).filter((r): r is PermissionRow => !!r),
    })),
    ...(orphans.length
      ? [
          {
            key: "khac",
            label: "Khác",
            noScope: false,
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

  // Vai mẫu: sau khi tách quyền theo màn, ma trận dài ~32 khoá. Cấp tay mất 10–15 phút và dễ
  // tick nhầm — mà rủi ro thật không phải mất thời gian, là người ta CẤP BỪA cho xong rồi còn
  // lỏng hơn trước khi tách. Mẫu chỉ ĐIỀN SẴN, người dùng xem lại rồi mới bấm Lưu.
  const coMau = !readOnly && !!templates?.length && !!onApplyTemplate;

  return (
    <div className="rdx-perm">
      {coMau && (
        <div className="rdx-perm__mau">
          <span className="rdx-perm__mau-nhan">Điền theo vai mẫu</span>
          <div className="rdx-perm__mau-nut">
            {templates!.map((t) => (
              <button
                key={t.key}
                type="button"
                className="rdx-perm__mau-btn"
                title={t.mo_ta}
                onClick={() => onApplyTemplate!(t)}
              >
                {t.label}
              </button>
            ))}
          </div>
          <p className="rdx-perm__mau-ghi">
            Chọn mẫu sẽ <strong>thay toàn bộ</strong> các ô bên dưới. Xem lại rồi bấm Lưu —
            chưa Lưu thì chưa có gì đổi.
          </p>
        </div>
      )}
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
              <div
                className={`rdx-perm__rows${g.noScope ? " rdx-perm__rows--noscope" : ""}`}
                role="group"
                aria-label={g.label}
              >
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
                  {!g.noScope && (
                    <span className="rdx-perm__c-scope">
                      Phạm vi
                      <span className="rdx-perm__fine-hint" title={COL_HINTS.scope}>
                        <Icon name="help" size={13} />
                      </span>
                    </span>
                  )}
                </div>
                {g.rows.map((row) => {
                  const label = moduleLabel.get(row.module_key) ?? row.module_key;
                  const isNoiQuy = row.module_key === "noi_quy";
                  const actionKeys: ActionKey[] = isNoiQuy
                    ? ["can_create", "can_delete"]
                    : WRITE_ACTIONS;
                  const canWrite = isNoiQuy
                    ? row.can_create && row.can_delete
                    : WRITE_ACTIONS.every((k) => row[k]);
                  const xemSong = oSong(row.module_key, "read");
                  // Cột "Thao tác" bật nhiều cột một lúc — coi là còn sống nếu CÓ ÍT NHẤT MỘT
                  // trong số đó được máy chủ gác. Đòi tất cả thì gần như màn nào cũng bị khoá oan.
                  const ghiSong = actionKeys.some((k) =>
                    oSong(row.module_key, k.replace("can_", "")),
                  );
                  const phamViChoPhep = PHAM_VI_CHO_PHEP[row.module_key];
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
                          <div className="rdx-perm__fixed-read">
                            <input
                              type="checkbox"
                              className="switch"
                              checked
                              disabled
                              aria-label={`Xem — ${label} — mọi nhân viên`}
                            />
                            <span className="rdx-perm__fixed-note">Mọi nhân viên</span>
                          </div>
                        ) : (
                          <input
                            type="checkbox"
                            className="switch"
                            checked={row.can_read && xemSong}
                            disabled={readOnly || !xemSong}
                            title={xemSong ? undefined : CANH_BAO_O_CHET}
                            aria-label={`Xem — ${label}`}
                            onChange={(e) =>
                              onToggle(row.module_key, "can_read", e.target.checked)
                            }
                          />
                        )}
                      </div>
                      <div className="rdx-perm__cell rdx-perm__cell--act">
                        <input
                          type="checkbox"
                          className="switch"
                          checked={canWrite && ghiSong}
                          disabled={readOnly || !ghiSong}
                          title={ghiSong ? undefined : CANH_BAO_O_CHET}
                          aria-label={
                            isNoiQuy
                              ? `Thao tác (thêm, xóa) — ${label}`
                              : `Chỉnh sửa (thêm, sửa, xóa) — ${label}`
                          }
                          onChange={(e) =>
                            actionKeys.forEach((k) =>
                              onToggle(row.module_key, k, e.target.checked),
                            )
                          }
                        />
                      </div>
                      {/* Nhóm `noScope` (Danh mục) KHÔNG dựng ô này. Trước 17/08/2026 chỉ tiêu đề
                          cột bị ẩn còn ô chọn vẫn render → lưới 3 cột đẩy nó rớt xuống dòng dưới,
                          nằm ngay dưới tên module. Người cấp quyền thấy một ô "Tất cả" tưởng chọn
                          được, trong khi `role_service.SCOPELESS_MODULES` ép `all` lúc lưu. */}
                      {!g.noScope && (
                        <div className="rdx-perm__cell rdx-perm__cell--scope">
                          <select
                            className="rdx-perm__scope"
                            value={row.scope}
                            // Chỉ còn ĐÚNG MỘT lựa chọn ⇒ khoá luôn: bày một ô chọn không chọn được
                            // gì khác chỉ làm người ta bấm thử rồi tưởng hỏng.
                            disabled={readOnly || phamViChoPhep?.length === 1}
                            title={
                              phamViChoPhep?.length === 1
                                ? "Màn này chỉ có một phạm vi hợp lý — không cần chọn."
                                : undefined
                            }
                            aria-label={`Phạm vi — ${label}`}
                            onChange={(e) => {
                              const moi = e.target.value as Scope;
                              // Hạ phạm vi khỏi "Tất cả" thì TỰ TẮT những ô đòi phạm vi toàn công
                              // ty (chủ chốt 15/08/2026). Để nguyên thì ô vẫn hiện là ĐANG BẬT
                              // nhưng bị làm mờ — nhìn như đã cấp, mà bấm vào ăn 403 vì máy chủ
                              // chặn. Tắt hẳn để cái nhìn thấy đúng bằng cái có thật.
                              if (moi !== "all") {
                                O_DOI_PHAM_VI_TOAN_CTY.forEach((k) => {
                                  if ((row as unknown as Record<string, boolean | undefined>)[k]) {
                                    onToggle(row.module_key, k as ActionKey, false);
                                  }
                                });
                              }
                              onScope(row.module_key, moi);
                            }}
                          >
                            {SCOPES.filter(
                              (s) => !phamViChoPhep || phamViChoPhep.includes(s.value),
                            ).map((s) => (
                              <option key={s.value} value={s.value}>
                                {s.label}
                              </option>
                            ))}
                          </select>
                        </div>
                      )}

                      {fineActs && fineIsOpen && (
                        <div className="rdx-perm__fine" role="group" aria-label={`Quyền chi tiết — ${label}`}>
                          {fineActs.map((a) => (
                            <label key={a.key} className="rdx-perm__fine-item">
                              <input
                                type="checkbox"
                                className="switch"
                                checked={fineOn(a) && oSong(row.module_key, a.key.replace("can_", ""))}
                                disabled={
                                  readOnly ||
                                  !oSong(row.module_key, a.key.replace("can_", "")) ||
                                  (O_DOI_PHAM_VI_TOAN_CTY.has(a.key) && row.scope !== "all")
                                }
                                title={
                                  O_DOI_PHAM_VI_TOAN_CTY.has(a.key) && row.scope !== "all"
                                    ? CANH_BAO_PHAM_VI
                                    : oSong(row.module_key, a.key.replace("can_", ""))
                                      ? a.hint
                                      : CANH_BAO_O_CHET
                                }
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
                                {/* Nói RA MẶT lý do không bật được — nằm trong tooltip thì người
                                    cấp quyền phải rê chuột mới biết, mà họ có biết đâu mà rê. */}
                                {O_DOI_PHAM_VI_TOAN_CTY.has(a.key) && row.scope !== "all" && (
                                  <span className="rdx-perm__fine-warn" title={CANH_BAO_PHAM_VI}>
                                    cần Phạm vi “Tất cả”
                                  </span>
                                )}
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
