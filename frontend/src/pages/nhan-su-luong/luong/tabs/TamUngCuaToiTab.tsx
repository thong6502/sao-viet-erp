// Tab Tạm ứng của tôi (tách từ pages/LuongPage.tsx).
import { useCallback, useEffect, useState } from "react";
import { Wallet } from "lucide-react";
import { api, type MyAdvances } from "../../../../api/client";
import { printAdvanceRequest } from "../../../../utils/printAdvanceRequest";
import { RowActionButton } from "../../../../components/RowActionButton";
import { advPrintData, money } from "../shared/helpers";
import { MyAdvanceModal } from "../modals/MyAdvanceModal";

// --- Tab: Tạm ứng của tôi (self-service — nhân viên tự đề nghị) --------------

export function TamUngCuaToiTab({
  token,
  eventTick,
  canCreate,
}: {
  token: string;
  eventTick?: number;
  /** Ô THAO TÁC của màn Lương. Không có ô thì KHÔNG bày nút — bày ra mà bấm ăn 403 thì
   *  trông như hệ thống hỏng, chứ không như "anh không có quyền" (chủ chốt 15/08/2026). */
  canCreate: boolean;
}) {
  const [data, setData] = useState<MyAdvances | null>(null);
  const [adding, setAdding] = useState<null | "tam_ung" | "luong_dot_1">(null);

  const load = useCallback(() => {
    api.luong
      .myAdvances(token)
      .then(setData)
      .catch(() => setData({ has_employee: false, items: [], luong_dot_1: 0 }));
  }, [token]);
  useEffect(() => {
    load();
  }, [load, eventTick]);

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

  if (!data)
    return (
      <p
        className="lg-payslip-empty-desc"
        style={{ textAlign: "center", marginTop: 24 }}
      >
        Đang tải…
      </p>
    );
  if (!data.has_employee)
    return (
      <div className="lg-table-empty-state">
        <div className="lg-table-empty-icon">
          <Wallet size={20} />
        </div>
        <span className="lg-table-empty-title">
          Tài khoản chưa gắn hồ sơ nhân sự
        </span>
        <span className="lg-table-empty-desc">
          Liên hệ HCNS để liên kết tài khoản với hồ sơ, sau đó mới lập đề nghị
          tạm ứng được.
        </span>
      </div>
    );
  return (
    <div>
      <div className="cc-toolbar lg-toolbar">
        {canCreate && (
          <button
            className="btn btn--primary"
            onClick={() => setAdding("tam_ung")}
          >
            + Đề nghị tạm ứng
          </button>
        )}
        {canCreate && (
          <button
            className="btn btn--ghost"
            onClick={() => setAdding("luong_dot_1")}
          >
            + Xin lương đợt 1
          </button>
        )}
        <span className="cc-card__hint">
          {canCreate
            ? "Đề nghị gửi tới kế toán duyệt; bấm “In phiếu” để ký & nộp."
            : "Chỉ xem — vai của bạn chưa được bật ô Thao tác ở màn Lương nên không gửi đề nghị được."}
        </span>
      </div>
      {data.items.length === 0 ? (
        <div className="lg-table-empty-state">
          <div className="lg-table-empty-icon">
            <Wallet size={20} />
          </div>
          <span className="lg-table-empty-title">Chưa có đề nghị tạm ứng</span>
          <span className="lg-table-empty-desc">
            Nhấp “+ Đề nghị tạm ứng” để lập phiếu gửi kế toán.
          </span>
        </div>
      ) : (
        <div className="lg-emp-table-wrapper">
          <table className="ns__table">
            <thead>
              <tr>
                <th>Mã</th>
                <th>Loại</th>
                <th>Kỳ</th>
                <th>Ngày ứng</th>
                <th className="lg-num">Số tiền</th>
                <th>Lý do</th>
                <th>Trạng thái</th>
                {/* "Thao tác" — tên cột thống nhất toàn hệ, KHÔNG dùng "Hành động". */}
                <th className="lg-actcol">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((a) => {
                const [label, cls] = STATUS[a.status] ?? [
                  a.status,
                  "ns-badge--muted",
                ];
                const [kLabel, kCls] = KIND[a.kind] ?? KIND.tam_ung;
                return (
                  <tr key={a.id}>
                    <td className="font-mono">{a.code ?? "—"}</td>
                    <td>
                      <span className={`ns-badge ${kCls}`}>{kLabel}</span>
                    </td>
                    <td>
                      {String(a.period_month).padStart(2, "0")}/{a.period_year}
                    </td>
                    <td>{a.advance_date}</td>
                    <td className="lg-num font-mono">{money(a.amount)}đ</td>
                    <td>{a.reason ?? "—"}</td>
                    <td>
                      <span className={`ns-badge ${cls}`}>{label}</span>
                    </td>
                    <td className="lg-rowact">
                      <RowActionButton
                        dense
                        label="In phiếu đề nghị"
                        icon="printer"
                        onClick={() => printAdvanceRequest(advPrintData(a))}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {adding && (
        <MyAdvanceModal
          token={token}
          kind={adding}
          dot1Prefill={data.luong_dot_1}
          kyMinServer={data.ky_min_chon_duoc ?? null}
          onClose={() => setAdding(null)}
          onSaved={() => {
            setAdding(null);
            load();
          }}
        />
      )}
    </div>
  );
}
