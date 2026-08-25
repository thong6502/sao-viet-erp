// Tab Tạm ứng (tách từ pages/LuongPage.tsx).
import { useCallback, useEffect, useState } from "react";
import { Calendar, Wallet } from "lucide-react";
import {
  api,
  type EmployeeRow,
  type PaymentVoucherRow,
  type SalaryAdvance,
} from "../../../../api/client";
import type { NavigateFn } from "../../../../components/AppShell";
import { MonthPicker } from "../../../../components/MonthPicker";
import { useCan } from "../../../../auth/permissions";
import { printAdvanceRequest } from "../../../../utils/printAdvanceRequest";
import { RowActionButton } from "../../../../components/RowActionButton";
import { advPrintData, curYm, errText, money } from "../shared/helpers";
import { AddAdvanceModal } from "../modals/AddAdvanceModal";
import { LapPhieuChiModal } from "../modals/LapPhieuChiModal";

// --- Tab: Tạm ứng -----------------------------------------------------------

export function TamUngTab({
  token,
  navigate,
  eventTick,
  canCreateAdvance,
  canApproveAdvance,
}: {
  token: string;
  navigate?: NavigateFn;
  eventTick?: number;
  canCreateAdvance: boolean;
  canApproveAdvance: boolean;
}) {
  const can = useCan();
  // Lập phiếu chi là việc của KẾ TOÁN, không phải của người duyệt tạm ứng (tách vai từ
  // 04/08/2026) ⇒ đi theo ô của phân hệ Phiếu chi, không theo `luong:approve`.
  const canLapPhieuChi = can("phieu_chi", "create");
  const canXemPhieuChi = can("phieu_chi", "read");
  const [ym, setYm] = useState(curYm);
  const [items, setItems] = useState<SalaryAdvance[]>([]);
  const [emps, setEmps] = useState<EmployeeRow[]>([]);
  const [adding, setAdding] = useState<null | "tam_ung" | "luong_dot_1">(null);
  // advance_id → phiếu chi CÒN HIỆU LỰC. Phiếu ĐÃ HUỶ bị loại ra vì backend cũng bỏ qua nó
  // (`get_voucher_by_salary_advance` lọc `status != cancelled`): huỷ phiếu chi xong là lập lại
  // được, chip phải biến mất theo — không thì kế toán tưởng đã chi rồi và bỏ sót tiền.
  const [pcTheoTamUng, setPcTheoTamUng] = useState<Map<number, PaymentVoucherRow>>(
    () => new Map(),
  );
  const [lapPcCho, setLapPcCho] = useState<SalaryAdvance | null>(null);
  const [pcVuaLap, setPcVuaLap] = useState<PaymentVoucherRow | null>(null);
  const [actErr, setActErr] = useState<string | null>(null);
  const [year, month] = ym.split("-").map(Number);

  const load = useCallback(() => {
    api.luong
      .advances(token, year, month)
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));
  }, [token, year, month]);
  // Danh sách tạm ứng CHƯA trả cờ "đã lập phiếu chi" ⇒ đối chiếu bằng sổ phiếu chi, map theo
  // `salary_advance_id`. Ai không có ô xem phiếu chi thì bỏ qua hẳn (gọi vào chỉ ăn 403).
  const loadPhieuChi = useCallback(() => {
    if (!canXemPhieuChi) {
      setPcTheoTamUng(new Map());
      return;
    }
    api.accounting
      .salaryAdvanceVouchers(token)
      .then((rows) => {
        const map = new Map<number, PaymentVoucherRow>();
        for (const pc of rows) {
          if (pc.salary_advance_id == null || pc.status === "cancelled") continue;
          map.set(pc.salary_advance_id, pc);
        }
        setPcTheoTamUng(map);
      })
      .catch(() => setPcTheoTamUng(new Map()));
  }, [token, canXemPhieuChi]);
  useEffect(() => {
    load();
    loadPhieuChi();
  }, [load, loadPhieuChi, eventTick]);
  useEffect(() => {
    api.employees
      .list(token, { size: 200, sort: "code" })
      .then((r) => setEmps(r.items))
      .catch(() => setEmps([]));
  }, [token]);

  async function act(fn: () => Promise<unknown>) {
    setActErr(null);
    try {
      await fn();
      load();
      loadPhieuChi();
    } catch (e) {
      // Nuốt lỗi ở đây là chỗ hỏng cũ: huỷ tạm ứng ĐÃ lập phiếu chi nay bị chặn 400 kèm CÂU
      // GIẢI THÍCH + mã phiếu chi ("… huỷ phiếu chi trước rồi mới huỷ được."). Hiện NGUYÊN CÂU
      // của backend — viết lại là mất mã phiếu, người dùng không biết phải huỷ cái nào.
      setActErr(errText(e));
    }
  }

  const STATUS: Record<string, [string, string]> = {
    pending: ["Chờ duyệt", "ns-badge--muted"],
    approved: ["Đã duyệt", "ns-badge--ok"],
    rejected: ["Từ chối", "ns-badge--danger"],
    cancelled: ["Đã hủy", "ns-badge--muted"],
  };
  const KIND: Record<string, [string, string]> = {
    tam_ung: ["Tạm ứng", "ns-badge--muted"],
    luong_dot_1: ["Lương đợt 1", "ns-badge--info"],
  };
  const totalApproved = items
    .filter((a) => a.status === "approved")
    .reduce((s, a) => s + a.amount, 0);

  return (
    <div>
      <div className="cc-toolbar cc-ts-toolbar lg-toolbar">
        <div className="lg-date-wrapper">
          <span className="lg-date-icon">
            <Calendar size={14} />
          </span>
          <MonthPicker value={ym} onChange={setYm} ariaLabel="Kỳ lương" />
        </div>
        {canCreateAdvance && (
          <button
            className="btn btn--primary"
            onClick={() => setAdding("tam_ung")}
          >
            + Thêm ứng
          </button>
        )}
        {canCreateAdvance && (
          <button
            className="btn btn--ghost"
            onClick={() => setAdding("luong_dot_1")}
          >
            + Phiếu lương đợt 1
          </button>
        )}
        <span className="lg-approved-badge">
          Đã duyệt: <b>{money(totalApproved)}đ</b>
        </span>
      </div>

      {actErr && (
        <div className="banner banner--error lg-tu-note">
          <span>{actErr}</span>
          <button
            type="button"
            className="lg-tu-note__x"
            aria-label="Đóng thông báo"
            onClick={() => setActErr(null)}
          >
            ×
          </button>
        </div>
      )}
      {/* Báo THÀNH CÔNG ở lại tới khi tự đóng (không tự tắt sau vài giây) vì nó mang MÃ PHIẾU
          CHI bấm được — mã trôi mất là kế toán phải đi tìm lại trong sổ quỹ. */}
      {pcVuaLap && (
        <div className="banner banner--success lg-tu-note">
          <span>
            Đã lập phiếu chi <b className="lg-tu-note__code">{pcVuaLap.code}</b>{" "}
            — {money(pcVuaLap.amount)}đ, tiền đã ra khỏi két.
          </span>
          {navigate && (
            <button
              type="button"
              className="lg-tu-note__link"
              onClick={() =>
                navigate("ke-toan-phieu-chi", {
                  focusVoucherQuery: pcVuaLap.code,
                })
              }
            >
              Mở phiếu chi
            </button>
          )}
          <button
            type="button"
            className="lg-tu-note__x"
            aria-label="Đóng thông báo"
            onClick={() => setPcVuaLap(null)}
          >
            ×
          </button>
        </div>
      )}

      {items.length === 0 ? (
        <div className="lg-table-empty-state">
          <div className="lg-table-empty-icon">
            <Wallet size={20} />
          </div>
          <span className="lg-table-empty-title">
            Chưa có tạm ứng tháng này
          </span>
          <span className="lg-table-empty-desc">
            Nhấp nút "+ Thêm ứng" để lập phiếu tạm ứng lương cho nhân viên trong
            kỳ.
          </span>
        </div>
      ) : (
        <div className="lg-emp-table-wrapper">
          <table className="ns__table">
            <thead>
              <tr>
                <th>Mã</th>
                <th>Nhân viên</th>
                <th>Loại</th>
                <th>Ngày ứng</th>
                <th className="lg-num">Số tiền</th>
                <th>Lý do</th>
                <th>Trạng thái</th>
                {/* "Thao tác" — tên cột thống nhất toàn hệ, KHÔNG dùng "Hành động". */}
                <th className="lg-actcol">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {items.map((a) => {
                const [label, cls] = STATUS[a.status] ?? [
                  a.status,
                  "ns-badge--muted",
                ];
                const [kLabel, kCls] = KIND[a.kind] ?? KIND.tam_ung;
                const pc = pcTheoTamUng.get(a.id) ?? null;
                return (
                  <tr key={a.id}>
                    <td className="font-mono">{a.code ?? "—"}</td>
                    <td>
                      <b>{a.employee_name ?? `NV#${a.employee_id}`}</b>
                    </td>
                    <td>
                      <span className={`ns-badge ${kCls}`}>{kLabel}</span>
                    </td>
                    <td>{a.advance_date}</td>
                    <td className="lg-num font-mono">{money(a.amount)}đ</td>
                    <td>{a.reason ?? "—"}</td>
                    <td>
                      <span className={`ns-badge ${cls}`}>{label}</span>
                    </td>
                    {/* Nút chữ trên dòng → `RowActionButton` dense. `danger` GIỮ NGUYÊN cho Từ
                        chối / Hủy: mất tín hiệu đỏ là bấm nhầm vào tiền của người ta. */}
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
                      {a.status === "approved" &&
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
                            onClick={() => setLapPcCho(a)}
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
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {adding && (
        <AddAdvanceModal
          token={token}
          emps={emps}
          year={year}
          month={month}
          kind={adding}
          onClose={() => setAdding(null)}
          onSaved={() => {
            setAdding(null);
            load();
          }}
        />
      )}

      {lapPcCho && (
        <LapPhieuChiModal
          token={token}
          adv={lapPcCho}
          onClose={() => setLapPcCho(null)}
          onDone={(pc) => {
            setLapPcCho(null);
            setActErr(null);
            setPcVuaLap(pc);
            loadPhieuChi();
          }}
        />
      )}
    </div>
  );
}
