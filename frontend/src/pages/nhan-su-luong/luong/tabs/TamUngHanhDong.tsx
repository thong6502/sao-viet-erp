// Ô "Thao tác" của một dòng ở tab Tạm ứng (chuyển nguyên từ TamUngTab.tsx 25/09/2026 để file
// chính dưới 400 dòng — không đổi hành vi).
import { api, type SalaryAdvance } from "../../../../api/client";
import type { NavigateFn } from "../../../../components/AppShell";
import { RowActionButton } from "../../../../components/RowActionButton";
import { printAdvanceRequest } from "../../../../utils/printAdvanceRequest";
import { advPrintData } from "../shared/helpers";

/** Nhãn + màu chip trạng thái / loại phiếu của tab Tạm ứng. */
export const STATUS: Record<string, [string, string]> = {
  pending: ["Chờ duyệt", "ns-badge--muted"],
  approved: ["Đã duyệt — chờ phiếu chi", "ns-badge--ok"],
  // Kế toán đã lập phiếu chi (07/09/2026): CHỈ phiếu này mới trừ vào lương.
  paid: ["Đã chi", "ns-badge--info"],
  rejected: ["Từ chối", "ns-badge--danger"],
  cancelled: ["Đã hủy", "ns-badge--muted"],
};
export const KIND: Record<string, [string, string]> = {
  tam_ung: ["Tạm ứng", "ns-badge--muted"],
  luong_dot_1: ["Lương đợt 1", "ns-badge--info"],
};

export function TamUngHanhDong({
  a,
  pc,
  navigate,
  canApproveAdvance,
  canLapPhieuChi,
  act,
  token,
  onLapPhieuChi,
}: {
  a: SalaryAdvance;
  /** Phiếu chi còn hiệu lực — máy chủ gắn sẵn trên dòng (`phieu_chi_id` / `phieu_chi_code`). */
  pc: { id: number; code: string } | null;
  navigate?: NavigateFn;
  canApproveAdvance: boolean;
  canLapPhieuChi: boolean;
  act: (fn: () => Promise<unknown>) => void;
  token: string;
  onLapPhieuChi: (a: SalaryAdvance) => void;
}) {
  // Nút chữ trên dòng → `RowActionButton` dense. `danger` GIỮ NGUYÊN cho Từ chối / Hủy: mất tín
  // hiệu đỏ là bấm nhầm vào tiền của người ta.
  return (
    <td className="lg-rowact">
      <RowActionButton
        dense
        label="In phiếu đề nghị"
        icon="printer"
        onClick={() => printAdvanceRequest(advPrintData(a))}
      />
      {canApproveAdvance && a.status === "pending" && (
        <>
          <RowActionButton
            dense
            label="Duyệt"
            icon="check"
            onClick={() =>
              act(() => api.luong.approveAdvance(token, a.id))
            }
          />
          <RowActionButton
            dense
            danger
            label="Từ chối"
            icon="x"
            onClick={() =>
              act(() => api.luong.rejectAdvance(token, a.id))
            }
          />
        </>
      )}
      {/* CHỈ phiếu ĐÃ DUYỆT mới ra được tiền. Đã có phiếu chi thì thay nút bằng
          CHIP mã phiếu — một phiếu tạm ứng chỉ một phiếu chi, bày nút lần hai chỉ
          để người ta bấm rồi ăn 409. */}
      {(a.status === "approved" || a.status === "paid") &&
        (pc ? (
          navigate ? (
            <button
              type="button"
              className="lg-pc-chip"
              title={`Mở phiếu chi ${pc.code} bên Kế toán`}
              onClick={() =>
                navigate("ke-toan-phieu-chi", {
                  focusVoucherQuery: pc.code,
                })
              }
            >
              {pc.code}
            </button>
          ) : (
            <span
              className="lg-pc-chip lg-pc-chip--static"
              title={`Đã lập phiếu chi ${pc.code}`}
            >
              {pc.code}
            </span>
          )
        ) : canLapPhieuChi ? (
          <RowActionButton
            dense
            variant="accent"
            label="Lập phiếu chi"
            icon="clipboard"
            onClick={() => onLapPhieuChi(a)}
          />
        ) : null)}
      {/* Đã lập phiếu chi thì backend chặn huỷ (400). Chặn luôn ở NÚT để lý do
          đọc được ngay trên tooltip — kèm MÃ phiếu chi, vì đó chính là thứ phải
          đi huỷ trước. Bấm được mà ăn lỗi thì `act()` vẫn hiện nguyên câu
          backend trả về. */}
      {canApproveAdvance && a.status === "approved" && (
        <RowActionButton
          dense
          danger
          disabled={pc != null}
          label={
            pc
              ? `Đã lập phiếu chi ${pc.code} — huỷ phiếu chi trước`
              : "Hủy phiếu đã duyệt"
          }
          icon="ban"
          onClick={() =>
            act(() => api.luong.cancelAdvance(token, a.id))
          }
        />
      )}
    </td>
  );
}

/** Dải thông báo có nút đóng (và một nút dẫn tuỳ chọn) — dùng chung cho các báo lỗi / thành công
 *  của tab Tạm ứng. Không tự tắt: báo thành công thường mang mã phiếu chi cần bấm theo. */
export function TuNote({
  tone,
  onClose,
  link,
  children,
}: {
  tone: "error" | "success";
  onClose: () => void;
  link?: { label: string; onClick: () => void } | null;
  children: React.ReactNode;
}) {
  return (
    <div className={`banner banner--${tone} lg-tu-note`}>
      <span>{children}</span>
      {link && (
        <button type="button" className="lg-tu-note__link" onClick={link.onClick}>
          {link.label}
        </button>
      )}
      <button type="button" className="lg-tu-note__x" aria-label="Đóng thông báo" onClick={onClose}>
        ×
      </button>
    </div>
  );
}
