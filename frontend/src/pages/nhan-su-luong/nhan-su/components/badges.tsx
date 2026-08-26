// Badge trạng thái · dải KPI · thẻ hoa hồng (tách từ pages/NhanSuPage.tsx).
import { useEffect, useState } from "react";
import { api, ApiError, type EmployeeKpis } from "../../../../api/client";
import {
  AlertCircle,
  Hourglass,
  TrendingUp,
  UserCheck,
  Users,
} from "lucide-react";
import { STATUS_CLASS, STATUS_LABEL } from "../shared/constants";
import { InfoCard, InfoField } from "./info-display";

export function StatusBadge({ status }: { status: string }) {
  const dotBg =
    status === "active"
      ? "#16a34a"
      : status === "probation"
      ? "#d97706"
      : status === "on_leave"
      ? "#9333ea"
      : status === "resigned"
      ? "#dc2626"
      : "#9ca3af";

  return (
    <span className={`ns-badge ${STATUS_CLASS[status] ?? "ns-badge--muted"}`}>
      <span className="ns-badge-dot" style={{ backgroundColor: dotBg }} />
      <span>{STATUS_LABEL[status] ?? status}</span>
    </span>
  );
}

export function KpiStrip({
  kpis,
  statusFilter,
  endingSoon,
  onPickAll,
  onPickProbation,
  onPickProbationEnded,
  onPickActive,
  onPickEndingSoon,
}: {
  kpis: EmployeeKpis;
  statusFilter: string;
  endingSoon: boolean;
  onPickAll: () => void;
  onPickProbation: () => void;
  onPickProbationEnded: () => void;
  onPickActive: () => void;
  onPickEndingSoon: () => void;
}) {
  const isAllActive = statusFilter === "" && !endingSoon;
  const isProbationActive = statusFilter === "probation" && !endingSoon;
  const isProbationEndedActive = statusFilter === "probation_ended" && !endingSoon;
  const isActiveActive = statusFilter === "active" && !endingSoon;
  const isEndingSoonActive = endingSoon;

  // "Sắp hết thử việc" = 0 thì KHÔNG tô cảnh báo: màu để dành cho lúc thật sự có việc.
  const endingSoonCount = kpis.probation_ending_soon;

  return (
    <div className="ns2__kpis" role="group" aria-label="Lọc nhanh theo trạng thái">
      <button
        type="button"
        className={`ns__kpi${isAllActive ? " is-active" : ""}`}
        onClick={onPickAll}
        aria-pressed={isAllActive}
        title="Xem tất cả nhân sự"
      >
        <Users size={13} aria-hidden="true" />
        <span className="ns__kpilabel">Tất cả</span>
        <span className="ns__kpival">{kpis.total}</span>
      </button>

      <button
        type="button"
        className={`ns__kpi${isProbationActive ? " is-active" : ""}`}
        onClick={onPickProbation}
        aria-pressed={isProbationActive}
        title="Chỉ xem người đang thử việc"
      >
        <Hourglass size={13} aria-hidden="true" />
        <span className="ns__kpilabel">Thử việc</span>
        <span className="ns__kpival">{kpis.probation}</span>
      </button>

      {/* Ô VIỆC TỒN: chỉ hiện khi có người thật sự đang chờ. Đây là cái duy nhất nhắc HCNS rằng
          có người đã hết hạn mà chưa ai bấm — 0 người thì giấu đi cho đỡ rác. */}
      {kpis.probation_ended > 0 && (
        <button
          type="button"
          className={`ns__kpi ns__kpi--due${isProbationEndedActive ? " is-active" : ""}`}
          onClick={onPickProbationEnded}
          aria-pressed={isProbationEndedActive}
          title="Đã hết thử việc, chờ bấm Chuyển chính thức"
        >
          <UserCheck size={13} aria-hidden="true" />
          <span className="ns__kpilabel">Chờ xác nhận</span>
          <span className="ns__kpival">{kpis.probation_ended}</span>
        </button>
      )}

      <button
        type="button"
        className={`ns__kpi${isActiveActive ? " is-active" : ""}`}
        onClick={onPickActive}
        aria-pressed={isActiveActive}
        title="Chỉ xem người đã chính thức"
      >
        <UserCheck size={13} aria-hidden="true" />
        <span className="ns__kpilabel">Chính thức</span>
        <span className="ns__kpival">{kpis.active}</span>
      </button>

      {/* Tách sang phải: đây là ô DUY NHẤT đòi người làm gì đó, không xếp lẫn 3 ô đếm kia. */}
      <button
        type="button"
        className={`ns__kpi ${isEndingSoonActive ? " is-active" : ""}`}
        onClick={onPickEndingSoon}
        aria-pressed={isEndingSoonActive}
        title={
          endingSoonCount === 0
            ? "Chưa có ai sắp hết thử việc trong 30 ngày tới"
            : `${endingSoonCount} người hết thử việc trong 30 ngày tới — cần quyết định ký chính thức`
        }
      >
        <AlertCircle size={13} aria-hidden="true" />
        <span className="ns__kpilabel">Sắp hết thử việc</span>
        <span className="ns__kpival">{endingSoonCount}</span>
      </button>
    </div>
  );
}

/** % hoa hồng của NV kinh doanh — CHỈ ĐỌC ở đây, sửa ở Lương → Lương nhân viên → Sửa lương.
 *  Không cho sửa tại drawer vì `POST /api/luong/salaries/{id}` luôn đẻ một mốc lương MỚI với
 *  TOÀN BỘ các số; drawer không giữ `luong_vi_tri`/phụ cấp nên post từ đây là lương về 0. */
export function CommissionCard({
  token,
  employeeId,
}: {
  token: string;
  employeeId: number;
}) {
  const [state, setState] = useState<
    | { kind: "loading" }
    | { kind: "forbidden" }
    | { kind: "ok"; pct: number | null }
    | { kind: "error" }
  >({ kind: "loading" });

  useEffect(() => {
    let alive = true;
    setState({ kind: "loading" });
    api.luong
      .salaries(token, employeeId)
      .then((r) => {
        if (!alive) return;
        const latest = r.items.length
          ? [...r.items].sort((a, b) =>
              b.effective_from.localeCompare(a.effective_from),
            )[0]
          : null;
        const pct = latest?.commission_pct ? latest.commission_pct * 100 : null;
        setState({ kind: "ok", pct });
      })
      .catch((e) => {
        if (!alive) return;
        // 403 ⇒ ẨN HẲN thẻ. Hiện "—" là NÓI DỐI: "—" nghĩa là chưa khai, còn ở đây là mình
        // không được phép biết — người xem sẽ kết luận nhầm là NV không có hoa hồng.
        if (e instanceof ApiError && e.status === 403)
          setState({ kind: "forbidden" });
        else setState({ kind: "error" });
      });
    return () => {
      alive = false;
    };
  }, [token, employeeId]);

  if (state.kind === "loading" || state.kind === "forbidden") return null;
  const pct = state.kind === "ok" ? state.pct : null;
  return (
    <InfoCard title="Hoa hồng kinh doanh" icon={TrendingUp}>
      <InfoField
        label="% hoa hồng"
        value={pct != null ? `${pct}%` : null}
        icon={TrendingUp}
        hint={
          "Chỉ để khai — hệ thống chưa tự cộng vào lương. Đổi ở Lương → Lương nhân viên → Sửa lương." +
          (state.kind === "error" ? " Không đọc được số hoa hồng." : "")
        }
      />
    </InfoCard>
  );
}
