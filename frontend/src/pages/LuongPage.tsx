// Lương (module `luong`, Phase 1 — lương thời gian). 5 tab:
//   • Bảng lương tháng — Tạo → soát ô vàng → Chốt → xuất Excel + file chuyển khoản.
//   • Lương nhân viên — khai báo (nhóm/bậc + mức) & điều chỉnh (lịch sử).
//   • Tạm ứng — ghi nhiều lần → duyệt → tự trừ.
//   • Quy tắc lương — tham số + bảng mức chuẩn.
//   • Phiếu lương của tôi — self-service.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Calendar,
  DollarSign,
  Users,
  Clock,
  TrendingDown,
  Search,
  Sliders,
  AlertTriangle,
  Wallet,
  FileText,
  Trash2,
} from "lucide-react";
import {
  api,
  type DepartmentSalaryRow,
  type EmployeeRow,
  type EmployeeSalary,
  type PayrollLine,
  type PayrollParams,
  type PayrollPeriod,
  type PitBracket,
  type PieceRate,
  type SalaryAdvance,
  type SalaryPreview,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { printAdvanceRequest } from "../utils/printAdvanceRequest";
import "./nhan-su.css";
import "./luong.css";

type Tab = "bang" | "nhanvien" | "khoan" | "tamung" | "quytac" | "phieu" | "tamung-me";

// Tổ khoán (đơn giá theo tổ) + đơn vị tính.
const KHOAN_GROUPS: { key: string; label: string }[] = [
  { key: "to_boi", label: "Tổ Bồi" },
  { key: "to_can_phu", label: "Tổ Cán/Phủ" },
  { key: "to_cat", label: "Tổ Cắt" },
  { key: "may_in_5mau", label: "Máy in 5 màu" },
  { key: "may_in_2mau", label: "Máy in 2 màu" },
  { key: "to_thanh_pham", label: "Tổ Thành phẩm" },
];
const KHOAN_GROUP_LABEL: Record<string, string> = Object.fromEntries(
  KHOAN_GROUPS.map((g) => [g.key, g.label]),
);
const UNIT_LABEL: Record<string, string> = {
  m2: "m²",
  bai_in: "bài in",
  tan: "tấn",
  cuon: "cuốn",
  luot: "lượt",
  hop: "hộp",
  to: "tờ",
  khac: "khác",
};

function money(n: number | null | undefined): string {
  if (n == null) return "0";
  return Math.round(n).toLocaleString("vi-VN");
}
function curYm(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
function errText(e: unknown): string {
  return e instanceof Error ? e.message : "Có lỗi xảy ra.";
}

export function LuongPage({
  focusEmployeeId,
  eventTick,
}: {
  focusEmployeeId?: number;
  /** Tăng mỗi sự kiện real-time (SSE) → tab Tạm ứng đang mở tự refetch, không cần đổi màn. */
  eventTick?: number;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canManage = can("luong", "update");
  const [tab, setTab] = useState<Tab>(canManage ? "bang" : "phieu");

  // Liên thông từ Hồ sơ nhân sự → mở tab "Lương nhân viên" tại đúng NV.
  useEffect(() => {
    if (focusEmployeeId && canManage) setTab("nhanvien");
  }, [focusEmployeeId, canManage]);

  return (
    <main className="ns">
      <header className="ns__head">
        <div>
          <h1 className="ns__title">Lương</h1>
          <p className="ns__sub">
            Bảng lương thời gian hàng tháng · tự kéo công từ Chấm công
          </p>
        </div>
      </header>

      <nav className="ns-tabs cc-tabs">
        {canManage && (
          <button
            className={tab === "bang" ? "is-active" : ""}
            onClick={() => setTab("bang")}
          >
            Bảng lương tháng
          </button>
        )}
        {canManage && (
          <button
            className={tab === "nhanvien" ? "is-active" : ""}
            onClick={() => setTab("nhanvien")}
          >
            Lương nhân viên
          </button>
        )}
        {canManage && (
          <button
            className={tab === "khoan" ? "is-active" : ""}
            onClick={() => setTab("khoan")}
          >
            Lương khoán
          </button>
        )}
        {canManage && (
          <button
            className={tab === "tamung" ? "is-active" : ""}
            onClick={() => setTab("tamung")}
          >
            Tạm ứng
          </button>
        )}
        {canManage && (
          <button
            className={tab === "quytac" ? "is-active" : ""}
            onClick={() => setTab("quytac")}
          >
            Quy tắc lương
          </button>
        )}
        <button
          className={tab === "phieu" ? "is-active" : ""}
          onClick={() => setTab("phieu")}
        >
          Phiếu lương của tôi
        </button>
        <button
          className={tab === "tamung-me" ? "is-active" : ""}
          onClick={() => setTab("tamung-me")}
        >
          Tạm ứng của tôi
        </button>
      </nav>

      {tab === "bang" && canManage && <BangLuongTab token={token!} />}
      {tab === "nhanvien" && canManage && (
        <NhanVienTab token={token!} focusEmployeeId={focusEmployeeId} />
      )}
      {tab === "khoan" && canManage && <KhoanTab token={token!} />}
      {tab === "tamung" && canManage && <TamUngTab token={token!} eventTick={eventTick} />}
      {tab === "quytac" && canManage && <QuyTacTab token={token!} />}
      {tab === "phieu" && <PhieuLuongTab token={token!} />}
      {tab === "tamung-me" && <TamUngCuaToiTab token={token!} eventTick={eventTick} />}
    </main>
  );
}

// --- Tab: Bảng lương tháng --------------------------------------------------

function BangLuongTab({ token }: { token: string }) {
  const [ym, setYm] = useState(curYm);
  const [period, setPeriod] = useState<PayrollPeriod | null>(null);
  const [lines, setLines] = useState<PayrollLine[]>([]);
  const [filter, setFilter] = useState<"all" | "ct" | "tv">("all");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState<PayrollLine | null>(null);
  const [printing, setPrinting] = useState<PayrollLine | null>(null);
  const [params, setParams] = useState<PayrollParams | null>(null);
  const [year, month] = ym.split("-").map(Number);

  useEffect(() => {
    api.luong
      .getParams(token)
      .then(setParams)
      .catch(() => setParams(null));
  }, [token]);

  const load = useCallback(() => {
    api.luong
      .table(token, year, month)
      .then((t) => {
        setPeriod(t.period);
        setLines(t.lines);
      })
      .catch(() => {
        setPeriod(null);
        setLines([]);
      });
  }, [token, year, month]);
  useEffect(() => {
    load();
  }, [load]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      load();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }

  const shown = lines.filter(
    (l) =>
      filter === "all" || (filter === "tv" ? l.is_probation : !l.is_probation),
  );
  const totalNet = shown.reduce((s, l) => s + l.net_pay, 0);
  const totalStaff = shown.length;
  const officialCount = shown.filter((l) => !l.is_probation).length;
  const probationCount = shown.filter((l) => l.is_probation).length;
  const totalWorkdays = shown.reduce((s, l) => s + (l.actual_cong ?? 0), 0);
  const totalDeductions = shown.reduce(
    (s, l) => s + (l.vi_pham ?? 0) + (l.bhxh ?? 0) + (l.advance_total ?? 0),
    0,
  );

  const status = period?.status;
  const isDraft = !period || status === "draft";
  const locked = status === "locked";
  const paid = status === "paid";

  async function downloadXlsx(kind: "table" | "bank") {
    setBusy(true);
    setErr(null);
    try {
      const url = await api.luong.xlsxBlobUrl(token, kind, year, month);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${kind === "bank" ? "chuyen-khoan" : "bang-luong"}-${ym}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="cc-toolbar cc-ts-toolbar lg-toolbar">
        <div className="lg-date-wrapper">
          <span className="lg-date-icon">
            <Calendar size={14} />
          </span>
          <input
            type="month"
            value={ym}
            onChange={(e) => setYm(e.target.value)}
          />
        </div>
        <div className="lg-seg">
          {(["all", "ct", "tv"] as const).map((f) => (
            <button
              key={f}
              className={filter === f ? "is-active" : ""}
              onClick={() => setFilter(f)}
            >
              {f === "all" ? "Tất cả" : f === "ct" ? "Chính thức" : "Thử việc"}
            </button>
          ))}
        </div>
        {isDraft && period && (
          <button
            className="btn btn--primary"
            onClick={() => run(() => api.luong.generate(token, year, month))}
            disabled={busy}
          >
            {busy ? "Đang tính…" : "↻ Tính lại"}
          </button>
        )}
        {period && isDraft && (
          <button
            className="btn btn--ghost"
            onClick={() => run(() => api.luong.lock(token, year, month))}
            disabled={busy}
          >
            🔒 Chốt
          </button>
        )}
        {locked && (
          <button
            className="btn btn--ghost"
            onClick={() => run(() => api.luong.reopen(token, year, month))}
            disabled={busy}
          >
            Mở lại
          </button>
        )}
        {locked && (
          <button
            className="btn btn--primary"
            onClick={() => run(() => api.luong.pay(token, year, month))}
            disabled={busy}
          >
            💵 Đã chi
          </button>
        )}
        {paid && (
          <button
            className="btn btn--ghost"
            onClick={() =>
              run(() => api.luong.unpay(token, year, month, "hủy đã chi"))
            }
            disabled={busy}
          >
            ↩ Hủy đã chi
          </button>
        )}
        {period && (
          <button
            className="btn btn--ghost"
            onClick={() => downloadXlsx("table")}
            disabled={busy}
          >
            ⬇ Xuất Excel
          </button>
        )}
        {(locked || paid) && (
          <button
            className="btn btn--ghost"
            onClick={() => downloadXlsx("bank")}
            disabled={busy}
          >
            ⬇ File chuyển khoản
          </button>
        )}
        {locked && <span className="ns-badge ns-badge--muted">Đã chốt</span>}
        {paid && (
          <span className="ns-badge ns-badge--muted">
            💵 Đã chi
            {period?.paid_at
              ? ` ${new Date(period.paid_at).toLocaleDateString("vi-VN")}`
              : ""}
          </span>
        )}
      </div>

      {err && (
        <div className="banner banner--error" style={{ marginBottom: 12 }}>
          {err}
        </div>
      )}

      {period && (
        <div className="lg-kpi-grid">
          <div className="lg-kpi-card lg-kpi-card--net">
            <div className="lg-kpi-card-header">
              <span className="lg-kpi-card-icon">
                <DollarSign size={15} />
              </span>
              <span className="lg-kpi-card-label">Tổng thực lĩnh</span>
            </div>
            <div className="lg-kpi-card-val">{money(totalNet)}đ</div>
            <div className="lg-kpi-card-sub">
              Chi trả cho {totalStaff} nhân sự
            </div>
          </div>

          <div className="lg-kpi-card lg-kpi-card--staff">
            <div className="lg-kpi-card-header">
              <span className="lg-kpi-card-icon">
                <Users size={15} />
              </span>
              <span className="lg-kpi-card-label">Quy mô nhân sự</span>
            </div>
            <div className="lg-kpi-card-val">{totalStaff} người</div>
            <div className="lg-kpi-card-sub">
              {officialCount} chính thức · {probationCount} thử việc
            </div>
          </div>

          <div className="lg-kpi-card lg-kpi-card--workday">
            <div className="lg-kpi-card-header">
              <span className="lg-kpi-card-icon">
                <Clock size={15} />
              </span>
              <span className="lg-kpi-card-label">Tổng ngày công</span>
            </div>
            <div className="lg-kpi-card-val">
              {totalWorkdays.toLocaleString("vi-VN")} công
            </div>
            <div className="lg-kpi-card-sub">
              Trung bình{" "}
              {(totalStaff ? totalWorkdays / totalStaff : 0).toFixed(1)}{" "}
              công/người
            </div>
          </div>

          <div className="lg-kpi-card lg-kpi-card--deduct">
            <div className="lg-kpi-card-header">
              <span className="lg-kpi-card-icon">
                <TrendingDown size={15} />
              </span>
              <span className="lg-kpi-card-label">Khấu trừ & Tạm ứng</span>
            </div>
            <div className="lg-kpi-card-val">−{money(totalDeductions)}đ</div>
            <div className="lg-kpi-card-sub">Bảo hiểm, phạt và ứng lương</div>
          </div>
        </div>
      )}

      {!period ? (
        <div className="lg-init-dashboard">
          <div className="lg-init-grid">
            <div className="lg-init-section lg-init-section--sources">
              <h3 className="lg-init-section-title">Dữ liệu nguồn đồng bộ</h3>
              <p className="lg-init-section-desc">
                Hệ thống tự động liên kết các phân hệ dữ liệu để tính toán lương
                chính xác:
              </p>

              <div className="lg-source-list">
                <div className="lg-source-item">
                  <div className="lg-source-item-head">
                    <span className="lg-source-bullet lg-source-bullet--active"></span>
                    <span className="lg-source-name">Dữ liệu Chấm công</span>
                  </div>
                  <span className="lg-source-text">
                    Lấy số ngày công thực tế, giờ tăng ca, số ngày làm ca đêm đã
                    chốt từ phân hệ Chấm công.
                  </span>
                </div>

                <div className="lg-source-item">
                  <div className="lg-source-item-head">
                    <span className="lg-source-bullet lg-source-bullet--active"></span>
                    <span className="lg-source-name">Quy tắc lương chuẩn</span>
                  </div>
                  <span className="lg-source-text">
                    Áp dụng mức lương chuẩn theo vị trí, tổ nhóm công tác, thâm
                    niên và giới tính đã cấu hình.
                  </span>
                </div>

                <div className="lg-source-item">
                  <div className="lg-source-item-head">
                    <span className="lg-source-bullet lg-source-bullet--active"></span>
                    <span className="lg-source-name">Khấu trừ & Tạm ứng</span>
                  </div>
                  <span className="lg-source-text">
                    Tự động trừ các khoản tạm ứng đã phê duyệt trong tháng, tính
                    BHXH bắt buộc và thuế TNCN lũy tiến.
                  </span>
                </div>
              </div>
            </div>

            <div className="lg-init-section lg-init-section--params">
              <h3 className="lg-init-section-title">
                Tham số cấu hình hiện tại
              </h3>
              <p className="lg-init-section-desc">
                Các tham số chung đang áp dụng trong hệ thống (sửa tại tab Quy
                tắc lương):
              </p>

              {params ? (
                <div className="lg-param-table">
                  <div className="lg-param-row">
                    <span className="lg-param-name">Công chuẩn mặc định</span>
                    <span className="lg-param-val">
                      {params.standard_cong_default} ngày
                    </span>
                  </div>
                  <div className="lg-param-row">
                    <span className="lg-param-name">Giờ công tiêu chuẩn</span>
                    <span className="lg-param-val">
                      {params.standard_hours_per_day}h/ngày
                    </span>
                  </div>
                  <div className="lg-param-row">
                    <span className="lg-param-name">Tỷ lệ lương thử việc</span>
                    <span className="lg-param-val">
                      {params.probation_ratio * 100}%
                    </span>
                  </div>
                  <div className="lg-param-row">
                    <span className="lg-param-name">Giảm trừ bản thân</span>
                    <span className="lg-param-val">
                      {money(params.deduction_self)}đ
                    </span>
                  </div>
                  <div className="lg-param-row">
                    <span className="lg-param-name">
                      Giảm trừ người phụ thuộc
                    </span>
                    <span className="lg-param-val">
                      {money(params.deduction_dependent)}đ
                    </span>
                  </div>
                </div>
              ) : (
                <p className="lg-param-loading">Đang tải tham số...</p>
              )}
            </div>
          </div>

          <div className="lg-init-action-card">
            <div className="lg-init-action-info">
              <h4 className="lg-init-action-title">
                Kỳ lương tháng {month}/{year} chưa được tạo
              </h4>
              <p className="lg-init-action-desc">
                Xác nhận các thông tin dữ liệu nguồn và tham số ở trên trước khi
                tiến hành khởi tạo.
              </p>
            </div>
            {isDraft && (
              <button
                className="btn btn--accent btn--large"
                onClick={() =>
                  run(() => api.luong.generate(token, year, month))
                }
                disabled={busy}
              >
                {busy ? "Đang tính toán..." : "Khởi tạo bảng lương"}
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="ns__tablewrap lg-table">
          <table className="ns__table">
            <thead>
              <tr>
                <th>Mã</th>
                <th>Họ tên</th>
                <th>Phòng/Tổ</th>
                <th className="lg-num">Công</th>
                <th className="lg-num">Lương công</th>
                <th className="lg-num">Chuyên cần</th>
                <th className="lg-num">Phụ cấp</th>
                <th className="lg-num">Khoán</th>
                <th className="lg-num">Tăng ca</th>
                <th className="lg-num">Ca đêm</th>
                <th className="lg-num">Vi phạm</th>
                <th className="lg-num">Thưởng</th>
                <th className="lg-num">BHXH</th>
                <th className="lg-num">Tạm ứng</th>
                <th className="lg-num lg-net">Thực lĩnh</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {shown.map((l) => (
                <tr key={l.id}>
                  <td className="ns__code">{l.employee_code}</td>
                  <td>
                    {l.employee_name}{" "}
                    {l.is_probation && (
                      <span className="ns-badge ns-badge--muted">TV</span>
                    )}
                  </td>
                  <td>{l.department_name ?? "—"}</td>
                  <td className="lg-num">{l.actual_cong}</td>
                  <td className="lg-num">{money(l.luong_cong)}</td>
                  <td className="lg-num">{money(l.chuyen_can)}</td>
                  <td className="lg-num">{money(l.allowance)}</td>
                  <td className="lg-num">{l.khoan ? money(l.khoan) : "—"}</td>
                  <td
                    className="lg-num"
                    title={
                      l.ot_minutes
                        ? `${(l.ot_minutes / 60).toFixed(1)}h tăng ca`
                        : ""
                    }
                  >
                    {l.ot_pay ? money(l.ot_pay) : "—"}
                  </td>
                  <td
                    className="lg-num"
                    title={l.night_days ? `${l.night_days} ngày ca đêm` : ""}
                  >
                    {l.night_pay ? money(l.night_pay) : "—"}
                  </td>
                  <td className={`lg-num ${l.vi_pham ? "lg-minus" : ""}`}>
                    {l.vi_pham ? "−" + money(l.vi_pham) : "—"}
                  </td>
                  <td className="lg-num">
                    {l.other_bonus ? money(l.other_bonus) : "—"}
                  </td>
                  <td className="lg-num lg-minus">
                    {l.bhxh ? "−" + money(l.bhxh) : "—"}
                  </td>
                  <td className={`lg-num ${l.advance_total ? "lg-minus" : ""}`}>
                    {l.advance_total ? "−" + money(l.advance_total) : "—"}
                  </td>
                  <td className="lg-num lg-net">{money(l.net_pay)}</td>
                  <td className="lg-rowact">
                    {!locked && (
                      <button
                        className="btn btn--ghost"
                        onClick={() => setEditing(l)}
                      >
                        Sửa
                      </button>
                    )}
                    <button className="btn btn--ghost" onClick={() => setPrinting(l)}>In</button>
                  </td>
                </tr>
              ))}
              {shown.length === 0 && (
                <tr>
                  <td colSpan={16} className="ns__empty">
                    Không có nhân viên phù hợp bộ lọc.
                  </td>
                </tr>
              )}
            </tbody>
            <tfoot>
              <tr className="lg-foot">
                <td colSpan={14}>Tổng thực lĩnh ({shown.length} người)</td>
                <td className="lg-num lg-net">{money(totalNet)}</td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {editing && (
        <LineEditModal
          token={token}
          line={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}

      {printing && period && (
        <div className="ns-modal" role="dialog" aria-modal="true">
          <div className="ns-modal__box ns-modal__box--wide">
            <header className="ns-modal__head lg-payslip-noprint">
              <h2>Phiếu lương — {printing.employee_name}</h2>
              <button className="ns-modal__x" onClick={() => setPrinting(null)}>×</button>
            </header>
            <div className="ns-modal__body">
              <PayslipCard line={printing} period={period} params={params} />
            </div>
            <footer className="ns-modal__foot lg-payslip-noprint">
              <button className="btn btn--ghost" onClick={() => setPrinting(null)}>Đóng</button>
              <button className="btn btn--primary" onClick={() => window.print()}>🖨 In phiếu</button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}

function LineEditModal({
  token,
  line,
  onClose,
  onSaved,
}: {
  token: string;
  line: PayrollLine;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [viPham, setViPham] = useState(line.vi_pham);
  const [bonus, setBonus] = useState(line.other_bonus);
  const [note, setNote] = useState(line.note ?? "");
  const [detail, setDetail] = useState({
    thuong_5s: line.thuong_5s, thuong_doanh_so: line.thuong_doanh_so,
    thuong_thanh_tich: line.thuong_thanh_tich, phep_nam: line.phep_nam,
    tra_dong_phuc: line.tra_dong_phuc,
    di_tre: line.di_tre, dt_vuot_troi: line.dt_vuot_troi,
    phat_bien_ban: line.phat_bien_ban, phat_5s_dong_phuc: line.phat_5s_dong_phuc,
  });
  const setD = (k: keyof typeof detail, v: number) => setDetail((d) => ({ ...d, [k]: v }));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      // TNCN LUÔN tự tính theo Biểu thuế lũy tiến — KHÔNG gửi `pit`; ép `pit_manual:false`
      // để backend tính lại TNCN theo thu nhập chịu thuế mới (không cho sửa tay).
      const input = { vi_pham: viPham, other_bonus: bonus, pit_manual: false, note: note || null, ...detail };
      await api.luong.updateLine(token, line.id, input);
      onSaved();
    } catch (e) {
      setErr(errText(e));
      setBusy(false);
    }
  }
  const bonusFields: [keyof typeof detail, string][] = [
    ["thuong_5s", "Thưởng 5S"],
    ["thuong_doanh_so", "Thưởng doanh số"],
    ["thuong_thanh_tich", "Thưởng thành tích"],
    ["phep_nam", "Phép năm"],
    ["tra_dong_phuc", "Trả đồng phục"],
  ];
  const penaltyFields: [keyof typeof detail, string][] = [
    ["di_tre", "Đi trễ / nghỉ KP"],
    ["dt_vuot_troi", "Điện thoại vượt trội"],
    ["phat_bien_ban", "Phạt biên bản"],
    ["phat_5s_dong_phuc", "Đồng phục / phạt 5S"],
  ];
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box ns-modal__box--wide">
        <header className="ns-modal__head">
          <h2>Sửa lương — {line.employee_name}</h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          <p className="cc-note">
            Lương công {money(line.luong_cong)} · chuyên cần{" "}
            {money(line.chuyen_can)} · phụ cấp {money(line.allowance)} · thu
            nhập tính thuế {money(line.pit_taxable)} → Thuế TNCN{" "}
            <b>{money(line.pit)}đ</b> (tự tính theo biểu thuế lũy tiến, không
            sửa).
          </p>
          <div className="ns-grid" style={{ marginTop: 12 }}>
            <label className="ns-field">
              <span className="ns-field__label">Giảm trừ khác (trừ)</span>
              <input
                type="number"
                min={0}
                value={viPham}
                onChange={(e) => setViPham(Number(e.target.value))}
              />
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Thưởng khác</span>
              <input
                type="number"
                min={0}
                value={bonus}
                onChange={(e) => setBonus(Number(e.target.value))}
              />
            </label>
          </div>
          <h4 className="ns-section__title" style={{ marginTop: 14 }}>Các khoản thưởng (cộng thu nhập)</h4>
          <div className="ns-grid">
            {bonusFields.map(([k, lbl]) => (
              <label className="ns-field" key={k}>
                <span className="ns-field__label">{lbl}</span>
                <input
                  type="number"
                  min={0}
                  value={detail[k]}
                  onChange={(e) => setD(k, Number(e.target.value))}
                />
              </label>
            ))}
          </div>
          <h4 className="ns-section__title" style={{ marginTop: 12 }}>Các khoản giảm trừ (phạt)</h4>
          <div className="ns-grid">
            {penaltyFields.map(([k, lbl]) => (
              <label className="ns-field" key={k}>
                <span className="ns-field__label">{lbl}</span>
                <input
                  type="number"
                  min={0}
                  value={detail[k]}
                  onChange={(e) => setD(k, Number(e.target.value))}
                />
              </label>
            ))}
          </div>
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Ghi chú</span>
            <input value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>
            {busy ? "Đang lưu…" : "Lưu"}
          </button>
        </footer>
      </div>
    </div>
  );
}

// --- Tab: Lương nhân viên ---------------------------------------------------

function NhanVienTab({
  token,
  focusEmployeeId,
}: {
  token: string;
  focusEmployeeId?: number;
}) {
  const [emps, setEmps] = useState<EmployeeRow[]>([]);
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<EmployeeRow | null>(null);

  const load = useCallback(() => {
    api.employees
      .list(token, { size: 200, sort: "code" })
      .then((r) => setEmps(r.items))
      .catch(() => setEmps([]));
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

  // Liên thông: khi mở từ Hồ sơ NV, tự bật modal lương của NV đó — CHỈ MỘT LẦN cho mỗi
  // focusEmployeeId. Không dùng ref-guard thì reload danh sách sau khi Đóng sẽ mở lại modal
  // (dep `emps` đổi) → tưởng "không đóng được".
  const autoOpenedFor = useRef<number | null>(null);
  useEffect(() => {
    if (
      focusEmployeeId &&
      emps.length &&
      autoOpenedFor.current !== focusEmployeeId
    ) {
      const e = emps.find((x) => x.id === focusEmployeeId);
      if (e) {
        setPicked(e);
        autoOpenedFor.current = focusEmployeeId;
      }
    }
  }, [focusEmployeeId, emps]);

  const shown = emps.filter(
    (e) =>
      !q ||
      e.full_name.toLowerCase().includes(q.toLowerCase()) ||
      e.code.includes(q),
  );

  return (
    <div>
      <div className="cc-toolbar">
        <div className="lg-search-wrapper">
          <span className="lg-search-icon">
            <Search size={14} />
          </span>
          <input
            className="lg-search-input"
            placeholder="Tìm theo tên / mã…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>
      <div className="lg-emp-table-wrapper">
        <table className="ns__table">
          <thead>
            <tr>
              <th>Mã</th>
              <th>Họ tên</th>
              <th>Vị trí</th>
              <th>Trạng thái</th>
              <th>Hành động</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((e) => {
              const statusLabels: Record<
                string,
                { label: string; className: string }
              > = {
                probation: {
                  label: "Thử việc",
                  className: "ns-badge ns-badge--warn",
                },
                active: {
                  label: "Chính thức",
                  className: "ns-badge ns-badge--ok",
                },
                on_leave: {
                  label: "Nghỉ phép",
                  className: "ns-badge ns-badge--info",
                },
                suspended: {
                  label: "Tạm đình chỉ",
                  className: "ns-badge ns-badge--danger",
                },
                resigned: {
                  label: "Đã thôi việc",
                  className: "ns-badge ns-badge--muted",
                },
              };
              const statusInfo = statusLabels[e.status] ?? {
                label: e.status,
                className: "ns-badge ns-badge--muted",
              };
              return (
                <tr key={e.id}>
                  <td className="ns__code">{e.code}</td>
                  <td>
                    <b>{e.full_name}</b>
                  </td>
                  <td>{e.position ?? "—"}</td>
                  <td>
                    <span className={statusInfo.className}>
                      {statusInfo.label}
                    </span>
                  </td>
                  <td>
                    <button
                      className="lg-edit-salary-btn"
                      onClick={() => setPicked(e)}
                    >
                      <Sliders size={13} /> Thiết lập lương
                    </button>
                  </td>
                </tr>
              );
            })}
            {shown.length === 0 && (
              <tr>
                <td colSpan={5} className="ns__empty">
                  Không có nhân viên.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {picked && (
        <SalaryModal
          token={token}
          emp={picked}
          onClose={() => {
            setPicked(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function SalaryModal({
  token,
  emp,
  onClose,
}: {
  token: string;
  emp: EmployeeRow;
  onClose: () => void;
}) {
  const [preview, setPreview] = useState<SalaryPreview | null>(null);
  const [history, setHistory] = useState<EmployeeSalary[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  // form khai/điều chỉnh lương
  const [effFrom, setEffFrom] = useState(
    () => `${new Date().getFullYear()}-01-01`,
  );
  const [mode, setMode] = useState<"manual" | "dept_row">("dept_row");
  const [baseAmount, setBaseAmount] = useState(0);
  const [insBase, setInsBase] = useState(0);
  const [allowance, setAllowance] = useState(0); // phụ cấp riêng NV
  const [chuyenCan, setChuyenCan] = useState(0); // chuyên cần riêng NV
  const [salaryRows, setSalaryRows] = useState<DepartmentSalaryRow[]>([]); // dòng bảng lương tổ của phòng NV
  const [salaryRowId, setSalaryRowId] = useState<number | "">("");
  const [params, setParams] = useState<PayrollParams | null>(null); // tỷ lệ BHXH/BHYT/BHTN + trần

  const reload = useCallback(async () => {
    const [detail, prev, hist] = await Promise.all([
      api.employees.get(token, emp.id),
      api.luong.salaryPreview(token, emp.id).catch(() => null),
      api.luong
        .salaries(token, emp.id)
        .catch(() => ({
          items: [] as EmployeeSalary[],
          employee_id: emp.id,
          employee_name: null,
        })),
    ]);
    setPreview(prev);
    setHistory(hist.items);
    // Nạp dòng bảng lương của tổ NV (để chọn/sửa mức theo dòng tổ).
    const rows = detail.department_id
      ? await api.luong
          .salaryRows(token, detail.department_id)
          .catch(() => [] as DepartmentSalaryRow[])
      : [];
    setSalaryRows(rows.filter((r) => r.is_active));
    // Điền sẵn theo bản lương mới nhất (để SỬA thay vì khai lại từ đầu).
    const latest = hist.items.length
      ? [...hist.items].sort((a, b) =>
          b.effective_from.localeCompare(a.effective_from),
        )[0]
      : null;
    if (latest) {
      setAllowance(latest.allowance ?? 0);
      setChuyenCan(latest.chuyen_can ?? 0);
      if (latest.insurance_base != null) setInsBase(latest.insurance_base);
      if (latest.amount_mode === "manual") {
        setMode("manual");
        setBaseAmount(latest.base_amount ?? 0);
      } else {
        setMode("dept_row");
        setSalaryRowId(latest.source_salary_row_id ?? "");
      }
    }
  }, [token, emp.id]);
  useEffect(() => {
    reload();
  }, [reload]);
  useEffect(() => {
    api.luong
      .getParams(token)
      .then(setParams)
      .catch(() => setParams(null));
  }, [token]);

  async function saveSalary() {
    if (mode === "dept_row" && salaryRowId === "") {
      setErr("Chọn 1 dòng bảng lương của tổ.");
      return;
    }
    setBusy(true);
    setErr(null);
    setOk(null);
    try {
      await api.luong.setSalary(token, emp.id, {
        effective_from: effFrom,
        amount_mode: mode,
        base_amount: mode === "manual" ? baseAmount : null,
        source_salary_row_id:
          mode === "dept_row" && salaryRowId !== "" ? salaryRowId : null,
        insurance_base: insBase || null,
        allowance,
        chuyen_can: chuyenCan,
      });
      setOk("Đã lưu lương (hiệu lực " + effFrom + ").");
      reload();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }

  // Tiền BHXH/BHYT/BHTN nhân viên đóng — theo TỶ LỆ đã cấu hình (Cấu hình tham số lương) + áp trần
  // RIÊNG đúng như engine (_compute). Mức nền BH = ô "Mức đóng BH" nếu >0, ngược lại = mức lương.
  const pickedRow = salaryRows.find((r) => r.id === salaryRowId);
  const salaryBase =
    mode === "manual"
      ? baseAmount
      : pickedRow
        ? pickedRow.luong_vi_tri + pickedRow.luong_trach_nhiem
        : (preview?.monthly ?? 0);
  const bhBase = insBase > 0 ? insBase : salaryBase;
  const isProbation = emp.status === "probation";
  const bhCapY =
    params && params.bh_base_cap > 0
      ? Math.min(bhBase, params.bh_base_cap)
      : bhBase;
  const bhCapTN =
    params && params.bhtn_base_cap > 0
      ? Math.min(bhBase, params.bhtn_base_cap)
      : bhBase;
  const bhxhAmt = params ? bhCapY * params.bhxh_rate : 0;
  const bhytAmt = params ? bhCapY * params.bhyt_rate : 0;
  const bhtnAmt = params ? bhCapTN * params.bhtn_rate : 0;
  const bhTotal = bhxhAmt + bhytAmt + bhtnAmt;
  const pctOf = (r: number) =>
    (r * 100).toLocaleString("vi-VN", { maximumFractionDigits: 2 });

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box ns-modal__box--wide">
        <header className="ns-modal__head">
          <h2>
            Lương — {emp.full_name} <span className="ns__code">{emp.code}</span>
          </h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          {ok && <div className="banner banner--ok">{ok}</div>}

          {preview && (
            <div className="lg-preview">
              Mức lương hiện tại: <b>{money(preview.monthly)}đ</b>{" "}
              <span className="ns-badge ns-badge--muted">
                {preview.source === "manual"
                  ? "nhập tay"
                  : preview.source === "dept_row"
                    ? "theo bảng lương tổ"
                    : preview.source === "rule"
                      ? "theo quy tắc"
                      : "chưa có"}
              </span>
              {" · "}phụ cấp {money(preview.allowance)} · đóng BH trên{" "}
              {money(preview.insurance_base)}
            </div>
          )}

          <h4 className="ns-section__title">Khai / Điều chỉnh lương</h4>
          <div className="ns-grid">
            <label className="ns-field">
              <span className="ns-field__label">Hiệu lực từ</span>
              <input
                type="date"
                value={effFrom}
                onChange={(e) => setEffFrom(e.target.value)}
              />
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Cách tính</span>
              <select
                value={mode}
                onChange={(e) =>
                  setMode(e.target.value as "manual" | "dept_row")
                }
              >
                <option value="dept_row">Theo bảng lương của tổ</option>
                <option value="manual">Nhập tay mức riêng</option>
              </select>
            </label>
            {mode === "manual" && (
              <label className="ns-field">
                <span className="ns-field__label">Mức lương tháng</span>
                <input
                  type="number"
                  min={0}
                  value={baseAmount}
                  onChange={(e) => setBaseAmount(Number(e.target.value))}
                />
              </label>
            )}
            {mode === "dept_row" && (
              <label className="ns-field">
                <span className="ns-field__label">
                  Mức từ bảng lương của tổ
                </span>
                <select
                  value={salaryRowId}
                  onChange={(e) =>
                    setSalaryRowId(
                      e.target.value === "" ? "" : Number(e.target.value),
                    )
                  }
                >
                  <option value="">— chọn dòng —</option>
                  {salaryRows.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.label} · {money(r.luong_vi_tri + r.luong_trach_nhiem)}đ
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label className="ns-field">
              <span className="ns-field__label">Phụ cấp (riêng người này)</span>
              <input
                type="number"
                min={0}
                value={allowance}
                onChange={(e) => setAllowance(Number(e.target.value))}
              />
            </label>
            {mode === "dept_row" && (
              <label className="ns-field">
                <span className="ns-field__label">
                  Chuyên cần (riêng người này)
                </span>
                <input
                  type="number"
                  min={0}
                  value={chuyenCan}
                  onChange={(e) => setChuyenCan(Number(e.target.value))}
                />
              </label>
            )}
            <label className="ns-field">
              <span className="ns-field__label">
                Mức đóng BH (0 = theo lương)
              </span>
              <input
                type="number"
                min={0}
                value={insBase}
                onChange={(e) => setInsBase(Number(e.target.value))}
              />
            </label>
            <div className="ns-field" style={{ justifyContent: "end" }}>
              <button
                className="btn btn--primary"
                onClick={saveSalary}
                disabled={busy}
              >
                Lưu điều chỉnh
              </button>
            </div>
          </div>

          {params && (
            <div className="lg-preview lg-bh" style={{ marginTop: 10 }}>
              {isProbation ? (
                <>
                  NV <b>thử việc</b> — chưa đóng BHXH/BHYT/BHTN (hợp đồng thử
                  việc).
                </>
              ) : (
                <>
                  {insBase > 0
                    ? "Đóng BH trên "
                    : "Để trống = đóng BH theo lương "}
                  <b>{money(bhBase)}đ</b>, nhân viên đóng gồm:
                  <br />· BHXH {pctOf(params.bhxh_rate)}% ={" "}
                  <b>{money(bhxhAmt)}đ</b>
                  {"  ·  "}BHYT {pctOf(params.bhyt_rate)}% ={" "}
                  <b>{money(bhytAmt)}đ</b>
                  {"  ·  "}BHTN {pctOf(params.bhtn_rate)}% ={" "}
                  <b>{money(bhtnAmt)}đ</b>
                  <br />→ Tổng nhân viên đóng: <b>{money(bhTotal)}đ/tháng</b>
                </>
              )}
            </div>
          )}

          <h4 className="ns-section__title" style={{ marginTop: 16 }}>
            Lịch sử điều chỉnh
          </h4>
          <div className="ns__tablewrap">
            <table className="ns__table">
              <thead>
                <tr>
                  <th>Hiệu lực từ</th>
                  <th>Cách tính</th>
                  <th className="lg-num">Mức tay</th>
                  <th className="lg-num">Phụ cấp</th>
                  <th>Ghi chú</th>
                </tr>
              </thead>
              <tbody>
                {history.map((s) => (
                  <tr key={s.id}>
                    <td>{s.effective_from}</td>
                    <td>
                      {s.amount_mode === "manual" ? "Nhập tay" : "Theo quy tắc"}
                    </td>
                    <td className="lg-num">
                      {s.base_amount != null ? money(s.base_amount) : "—"}
                    </td>
                    <td className="lg-num">{money(s.allowance)}</td>
                    <td>{s.note ?? "—"}</td>
                  </tr>
                ))}
                {history.length === 0 && (
                  <tr>
                    <td colSpan={5} className="ns__empty">
                      Chưa khai lương.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>
            Đóng
          </button>
        </footer>
      </div>
    </div>
  );
}

// --- Tab: Lương khoán (đơn giá khoán) ---------------------------------------
// Tiền khoán mỗi người = Phiếu sản lượng theo người (màn Lệnh SX) → cột "Khoán" bảng lương.
// Tab này chỉ quản lý bảng ĐƠN GIÁ khoán để tra khi ghi phiếu.

function KhoanTab({ token }: { token: string }) {
  return <KhoanRates token={token} />;
}

function KhoanRates({ token }: { token: string }) {
  const [rates, setRates] = useState<PieceRate[]>([]);
  const [editing, setEditing] = useState<PieceRate | "new" | null>(null);
  const load = useCallback(() => {
    api.luong
      .khoanRates(token)
      .then((r) => setRates(r.items))
      .catch(() => setRates([]));
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);
  async function remove(id: number) {
    await api.luong.deleteKhoanRate(token, id);
    load();
  }

  return (
    <div>
      <div className="cc-toolbar">
        <h4 className="ns-section__title" style={{ margin: 0, flex: 1 }}>
          Đơn giá khoán theo tổ
        </h4>
        <button className="btn btn--primary" onClick={() => setEditing("new")}>
          + Thêm đơn giá
        </button>
      </div>
      <div className="ns__tablewrap">
        <table className="ns__table">
          <thead>
            <tr>
              <th>Tổ</th>
              <th>Mã</th>
              <th>Công việc</th>
              <th>Đơn vị</th>
              <th className="lg-num">Đơn giá</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rates.map((r) => (
              <tr key={r.id}>
                <td>{KHOAN_GROUP_LABEL[r.group_name] ?? r.group_name}</td>
                <td>{r.code ?? "—"}</td>
                <td>{r.name}</td>
                <td>{UNIT_LABEL[r.unit] ?? r.unit}</td>
                <td className="lg-num">{money(r.unit_price)}</td>
                <td className="cc-rowact">
                  <button
                    className="btn btn--ghost"
                    onClick={() => setEditing(r)}
                  >
                    Sửa
                  </button>
                  <button
                    className="btn btn--ghost ns-danger"
                    onClick={() => remove(r.id)}
                  >
                    Xóa
                  </button>
                </td>
              </tr>
            ))}
            {rates.length === 0 && (
              <tr>
                <td colSpan={6} className="ns__empty">
                  Chưa có đơn giá khoán nào.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {editing && (
        <KhoanRateModal
          token={token}
          rate={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function KhoanRateModal({
  token,
  rate,
  onClose,
  onSaved,
}: {
  token: string;
  rate: PieceRate | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [group, setGroup] = useState(rate?.group_name ?? KHOAN_GROUPS[0].key);
  const [code, setCode] = useState(rate?.code ?? "");
  const [name, setName] = useState(rate?.name ?? "");
  const [unit, setUnit] = useState(rate?.unit ?? "m2");
  const [price, setPrice] = useState(rate?.unit_price ?? 0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setErr(null);
    const input = {
      group_name: group,
      code: code || null,
      name,
      unit,
      unit_price: price,
      is_active: true,
    };
    try {
      if (rate) await api.luong.updateKhoanRate(token, rate.id, input);
      else await api.luong.createKhoanRate(token, input);
      onSaved();
    } catch (e) {
      setErr(errText(e));
      setBusy(false);
    }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>{rate ? "Sửa đơn giá khoán" : "Thêm đơn giá khoán"}</h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          <div className="ns-grid">
            <label className="ns-field">
              <span className="ns-field__label">Tổ *</span>
              <select value={group} onChange={(e) => setGroup(e.target.value)}>
                {KHOAN_GROUPS.map((g) => (
                  <option key={g.key} value={g.key}>
                    {g.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Mã (A–F, nếu có)</span>
              <input value={code} onChange={(e) => setCode(e.target.value)} />
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Đơn vị</span>
              <select value={unit} onChange={(e) => setUnit(e.target.value)}>
                {Object.entries(UNIT_LABEL).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Đơn giá/đơn vị *</span>
              <input
                type="number"
                min={0}
                value={price}
                onChange={(e) => setPrice(Number(e.target.value))}
              />
            </label>
          </div>
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Công việc *</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="vd: Bồi carton 3 lớp E,B"
            />
          </label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>
            {busy ? "Đang lưu…" : "Lưu"}
          </button>
        </footer>
      </div>
    </div>
  );
}

// --- Tab: Tạm ứng -----------------------------------------------------------

/** Map 1 bản ghi tạm ứng → dữ liệu phiếu in "Giấy đề nghị tạm ứng". */
function advPrintData(a: SalaryAdvance) {
  return {
    code: a.code,
    employeeName: a.employee_name,
    departmentName: a.department_name,
    bankAccount: a.bank_account,
    bankName: a.bank_name,
    amount: a.amount,
    advanceDate: a.advance_date,
    periodMonth: a.period_month,
    periodYear: a.period_year,
    reason: a.reason,
  };
}

function TamUngTab({ token, eventTick }: { token: string; eventTick?: number }) {
  const [ym, setYm] = useState(curYm);
  const [items, setItems] = useState<SalaryAdvance[]>([]);
  const [emps, setEmps] = useState<EmployeeRow[]>([]);
  const [adding, setAdding] = useState(false);
  const [year, month] = ym.split("-").map(Number);

  const load = useCallback(() => {
    api.luong
      .advances(token, year, month)
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));
  }, [token, year, month]);
  useEffect(() => {
    load();
  }, [load, eventTick]);
  useEffect(() => {
    api.employees
      .list(token, { size: 200, sort: "code" })
      .then((r) => setEmps(r.items))
      .catch(() => setEmps([]));
  }, [token]);

  async function act(fn: () => Promise<unknown>) {
    try {
      await fn();
      load();
    } catch {
      /* ignore */
    }
  }

  const STATUS: Record<string, [string, string]> = {
    pending: ["Chờ duyệt", "ns-badge--muted"],
    approved: ["Đã duyệt", "ns-badge--ok"],
    rejected: ["Từ chối", "ns-badge--danger"],
    cancelled: ["Đã hủy", "ns-badge--muted"],
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
          <input
            type="month"
            value={ym}
            onChange={(e) => setYm(e.target.value)}
          />
        </div>
        <button className="btn btn--primary" onClick={() => setAdding(true)}>
          + Thêm ứng
        </button>
        <span className="lg-approved-badge">
          Đã duyệt: <b>{money(totalApproved)}đ</b>
        </span>
      </div>

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
                <th>Ngày ứng</th>
                <th className="lg-num">Số tiền</th>
                <th>Lý do</th>
                <th>Trạng thái</th>
                <th>Hành động</th>
              </tr>
            </thead>
            <tbody>
              {items.map((a) => {
                const [label, cls] = STATUS[a.status] ?? [
                  a.status,
                  "ns-badge--muted",
                ];
                return (
                  <tr key={a.id}>
                    <td className="font-mono">{a.code ?? "—"}</td>
                    <td>
                      <b>{a.employee_name ?? `NV#${a.employee_id}`}</b>
                    </td>
                    <td>{a.advance_date}</td>
                    <td className="lg-num font-mono">{money(a.amount)}đ</td>
                    <td>{a.reason ?? "—"}</td>
                    <td>
                      <span className={`ns-badge ${cls}`}>{label}</span>
                    </td>
                    <td className="cc-rowact">
                      <button
                        className="btn btn--ghost"
                        onClick={() => printAdvanceRequest(advPrintData(a))}
                      >
                        🖨 In phiếu
                      </button>
                      {a.status === "pending" && (
                        <>
                          <button
                            className="btn btn--ghost"
                            onClick={() =>
                              act(() => api.luong.approveAdvance(token, a.id))
                            }
                          >
                            Duyệt
                          </button>
                          <button
                            className="btn btn--ghost ns-danger"
                            onClick={() =>
                              act(() => api.luong.rejectAdvance(token, a.id))
                            }
                          >
                            Từ chối
                          </button>
                        </>
                      )}
                      {a.status === "approved" && (
                        <button
                          className="btn btn--ghost ns-danger"
                          onClick={() =>
                            act(() => api.luong.cancelAdvance(token, a.id))
                          }
                        >
                          Hủy
                        </button>
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
          onClose={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            load();
          }}
        />
      )}
    </div>
  );
}

function AddAdvanceModal({
  token,
  emps,
  year,
  month,
  onClose,
  onSaved,
}: {
  token: string;
  emps: EmployeeRow[];
  year: number;
  month: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [empId, setEmpId] = useState<number | "">("");
  const [amount, setAmount] = useState(0);
  const [dateStr, setDateStr] = useState(() =>
    new Date().toISOString().slice(0, 10),
  );
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    if (empId === "" || amount <= 0) {
      setErr("Chọn nhân viên và nhập số tiền > 0.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api.luong.createAdvance(token, {
        employee_id: Number(empId),
        period_year: year,
        period_month: month,
        advance_date: dateStr,
        amount,
        reason: reason || null,
      });
      onSaved();
    } catch (e) {
      setErr(errText(e));
      setBusy(false);
    }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>
            Thêm tạm ứng — {String(month).padStart(2, "0")}/{year}
          </h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          <label className="ns-field">
            <span className="ns-field__label">Nhân viên *</span>
            <select
              value={empId}
              onChange={(e) =>
                setEmpId(e.target.value ? Number(e.target.value) : "")
              }
            >
              <option value="">— chọn —</option>
              {emps.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.code} · {e.full_name}
                </option>
              ))}
            </select>
          </label>
          <div className="ns-grid" style={{ marginTop: 12 }}>
            <label className="ns-field">
              <span className="ns-field__label">Số tiền *</span>
              <input
                type="number"
                min={0}
                value={amount}
                onChange={(e) => setAmount(Number(e.target.value))}
              />
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Ngày ứng</span>
              <input
                type="date"
                value={dateStr}
                onChange={(e) => setDateStr(e.target.value)}
              />
            </label>
          </div>
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Lý do</span>
            <input value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>
            {busy ? "Đang lưu…" : "Lưu"}
          </button>
        </footer>
      </div>
    </div>
  );
}

// --- Tab: Quy tắc lương -----------------------------------------------------

function QuyTacTab({ token }: { token: string }) {
  const [params, setParams] = useState<PayrollParams | null>(null);
  const [brackets, setBrackets] = useState<PitBracket[]>([]);
  const [paramsModalOpen, setParamsModalOpen] = useState(false);
  const [ok, setOk] = useState<string | null>(null);

  const load = useCallback(() => {
    api.luong
      .getParams(token)
      .then(setParams)
      .catch(() => setParams(null));
    api.luong
      .pitBrackets(token)
      .then((r) => setBrackets(r.items))
      .catch(() => setBrackets([]));
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

  async function saveBrackets() {
    for (const b of brackets)
      await api.luong.updatePitBracket(token, b.id, {
        seq: b.seq,
        up_to: b.up_to,
        rate: b.rate,
      });
    setOk("Đã lưu biểu thuế TNCN.");
    setTimeout(() => setOk(null), 2000);
    load();
  }
  async function addBracket() {
    await api.luong.createPitBracket(token, {
      seq: brackets.length + 1,
      up_to: null,
      rate: 0.35,
    });
    load();
  }
  async function removeBracket(id: number) {
    await api.luong.deletePitBracket(token, id);
    load();
  }

  return (
    <div>
      {ok && (
        <div className="banner banner--ok" style={{ marginBottom: 12 }}>
          {ok}
        </div>
      )}
      {params && (
        <div className="lg-params-summary-card">
          <div className="lg-summary-info">
            <h4 className="lg-summary-title">Tham số chung hệ thống</h4>
            <p className="lg-summary-desc">
              Tham số phục vụ tính công chuẩn, bảo hiểm nhân viên và khấu trừ
              thuế TNCN.
            </p>
          </div>
          <div className="lg-summary-grid">
            <div className="lg-summary-item">
              <span className="lg-summary-label">Công chuẩn mặc định</span>
              <span className="lg-summary-value">
                {params.standard_cong_default} công /{" "}
                {params.standard_hours_per_day}h
              </span>
            </div>
            <div className="lg-summary-item">
              <span className="lg-summary-label">Đóng BHXH (Nhân viên)</span>
              <span className="lg-summary-value">
                {(params.bhxh_rate * 100).toFixed(1)}%
              </span>
            </div>
            <div className="lg-summary-item">
              <span className="lg-summary-label">Giảm trừ gia cảnh</span>
              <span className="lg-summary-value">
                {money(params.deduction_self)}đ
              </span>
            </div>
            <div className="lg-summary-item">
              <span className="lg-summary-label">Lương thử việc</span>
              <span className="lg-summary-value">
                {(params.probation_ratio * 100).toFixed(0)}%
              </span>
            </div>
          </div>
          <div className="lg-summary-action">
            <button
              className="btn btn--secondary"
              onClick={() => setParamsModalOpen(true)}
            >
              <Sliders size={13} /> Cấu hình tham số
            </button>
          </div>
        </div>
      )}

      <div className="lg-tncn-wrapper">
        <h4 className="lg-tncn-title">
          Biểu thuế TNCN (lũy tiến từng phần, biểu tháng)
        </h4>
        <p className="lg-tncn-desc">
          Thu nhập tính thuế = thu nhập chịu thuế − BHXH − giảm trừ. Sửa khi
          luật đổi (mặc định 2026: Luật 109/2025).
        </p>
        <div
          className="ns__tablewrap"
          style={{
            border: "1px solid var(--rule-soft)",
            borderRadius: "var(--r-3)",
            overflow: "hidden",
          }}
        >
          <table className="lg-tncn-table">
            <thead>
              <tr>
                <th style={{ width: 80 }}>Bậc</th>
                <th>Đến mức (thu nhập tính thuế/tháng)</th>
                <th style={{ width: 180 }}>Thuế suất %</th>
                <th style={{ width: 60, textAlign: "center" }}>Hành động</th>
              </tr>
            </thead>
            <tbody>
              {brackets.map((b, i) => (
                <tr key={b.id}>
                  <td style={{ verticalAlign: "middle" }}>
                    <b>Bậc {b.seq}</b>
                  </td>
                  <td>
                    <div className="lg-input-wrapper">
                      <input
                        type="number"
                        min={0}
                        value={b.up_to ?? ""}
                        placeholder="∞ (bậc cao nhất)"
                        onChange={(e) =>
                          setBrackets(
                            brackets.map((x, j) =>
                              j === i
                                ? {
                                    ...x,
                                    up_to:
                                      e.target.value === ""
                                        ? null
                                        : Number(e.target.value),
                                  }
                                : x,
                            ),
                          )
                        }
                      />
                      {b.up_to !== null && (
                        <span className="lg-input-suffix">đ</span>
                      )}
                    </div>
                    {b.up_to !== null && (
                      <div className="lg-input-helper">{money(b.up_to)}đ</div>
                    )}
                  </td>
                  <td>
                    <div className="lg-input-wrapper">
                      <input
                        type="number"
                        min={0}
                        step={1}
                        value={Math.round(b.rate * 100)}
                        onChange={(e) =>
                          setBrackets(
                            brackets.map((x, j) =>
                              j === i
                                ? { ...x, rate: Number(e.target.value) / 100 }
                                : x,
                            ),
                          )
                        }
                      />
                      <span className="lg-input-suffix">%</span>
                    </div>
                  </td>
                  <td style={{ textAlign: "center", verticalAlign: "middle" }}>
                    <button
                      className="lg-btn-delete-bracket"
                      title="Xóa bậc này"
                      onClick={() => removeBracket(b.id)}
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
          <button className="btn btn--primary" onClick={saveBrackets}>
            Lưu biểu thuế
          </button>
          <button className="btn btn--ghost" onClick={addBracket}>
            + Thêm bậc
          </button>
        </div>
      </div>

      {paramsModalOpen && params && (
        <ParamsModal token={token} params={params} onClose={() => setParamsModalOpen(false)} onSaved={() => { setParamsModalOpen(false); load(); setOk("Đã lưu tham số."); setTimeout(() => setOk(null), 2000); }} />
      )}
    </div>
  );
}

function NumField({
  label,
  v,
  on,
  step,
  suffix,
  isPercent,
}: {
  label: string;
  v: number;
  on: (x: number) => void;
  step?: number;
  suffix?: string;
  isPercent?: boolean;
}) {
  const displayVal = isPercent ? Number((v * 100).toFixed(3)) : v;

  const handleChange = (valStr: string) => {
    const num = Number(valStr);
    if (isPercent) {
      on(num / 100);
    } else {
      on(num);
    }
  };

  const renderHelperText = () => {
    if (suffix === "đ" && v > 0) return money(v) + " đ";
    return "";
  };

  return (
    <div className="lg-field-wrapper">
      <span className="lg-field-label">{label}</span>
      <div className="lg-input-wrapper">
        <input
          type="number"
          step={step ?? (isPercent ? 1 : 1)}
          value={displayVal}
          onChange={(e) => handleChange(e.target.value)}
        />
        {(suffix || isPercent) && (
          <span className="lg-input-suffix">{suffix ?? "%"}</span>
        )}
      </div>
      <div className="lg-input-helper">{renderHelperText()}</div>
    </div>
  );
}

function ParamsModal({
  token,
  params: initialParams,
  onClose,
  onSaved,
}: {
  token: string;
  params: PayrollParams;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [params, setParams] = useState<PayrollParams>({ ...initialParams });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      await api.luong.updateParams(token, params);
      onSaved();
    } catch (e) {
      setErr(errText(e));
      setBusy(false);
    }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div
        className="ns-modal__box ns-modal__box--wide"
        style={{ maxWidth: 1000 }}
      >
        <header className="ns-modal__head">
          <h2>Cấu hình tham số lương chung</h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div
          className="ns-modal__body"
          style={{ maxHeight: "calc(100vh - 200px)", overflowY: "auto" }}
        >
          {err && <div className="banner banner--error">{err}</div>}
          <div className="lg-rules-grid">
            <div className="lg-params-card">
              <h4 className="lg-params-card-title">
                Cấu hình Lao động & Tăng ca
              </h4>
              <div className="lg-params-fields">
                <NumField
                  label="Công chuẩn mặc định/tháng"
                  suffix="công"
                  v={params.standard_cong_default}
                  on={(x) => setParams({ ...params, standard_cong_default: x })}
                />
                <NumField
                  label="Giờ công tiêu chuẩn/ngày"
                  suffix="h"
                  v={params.standard_hours_per_day}
                  step={0.5}
                  on={(x) =>
                    setParams({ ...params, standard_hours_per_day: x })
                  }
                />
                <NumField
                  label="Hệ số tăng ca ngày thường"
                  suffix="x"
                  v={params.ot_multiplier}
                  step={0.1}
                  on={(x) => setParams({ ...params, ot_multiplier: x })}
                />
                <NumField
                  label="Hệ số tăng ca ngày nghỉ tuần"
                  suffix="x"
                  v={params.ot_multiplier_restday}
                  step={0.1}
                  on={(x) => setParams({ ...params, ot_multiplier_restday: x })}
                />
                <NumField
                  label="Hệ số tăng ca ngày lễ"
                  suffix="x"
                  v={params.ot_multiplier_holiday}
                  step={0.1}
                  on={(x) => setParams({ ...params, ot_multiplier_holiday: x })}
                />
                <NumField
                  label="Tỷ lệ phụ cấp ca đêm"
                  isPercent
                  v={params.night_pct}
                  step={5}
                  on={(x) => setParams({ ...params, night_pct: x })}
                />
                <NumField
                  label="Tỷ lệ lương thử việc"
                  isPercent
                  v={params.probation_ratio}
                  step={5}
                  on={(x) => setParams({ ...params, probation_ratio: x })}
                />
              </div>
            </div>

            <div className="lg-params-card">
              <h4 className="lg-params-card-title">Cấu hình Đóng Bảo hiểm</h4>
              <div className="lg-params-fields">
                <NumField
                  label="Tỷ lệ BHXH (Nhân viên)"
                  isPercent
                  v={params.bhxh_rate}
                  step={0.5}
                  on={(x) => setParams({ ...params, bhxh_rate: x })}
                />
                <NumField
                  label="Tỷ lệ BHYT (Nhân viên)"
                  isPercent
                  v={params.bhyt_rate}
                  step={0.5}
                  on={(x) => setParams({ ...params, bhyt_rate: x })}
                />
                <NumField
                  label="Tỷ lệ BHTN (Nhân viên)"
                  isPercent
                  v={params.bhtn_rate}
                  step={0.5}
                  on={(x) => setParams({ ...params, bhtn_rate: x })}
                />
                <NumField
                  label="Tỷ lệ công đoàn (Nhân viên)"
                  isPercent
                  v={params.cong_doan_rate}
                  step={0.5}
                  on={(x) => setParams({ ...params, cong_doan_rate: x })}
                />
                <NumField
                  label="Trần đóng BHXH/BHYT"
                  suffix="đ"
                  v={params.bh_base_cap}
                  on={(x) => setParams({ ...params, bh_base_cap: x })}
                />
                <NumField
                  label="Trần đóng BHTN"
                  suffix="đ"
                  v={params.bhtn_base_cap}
                  on={(x) => setParams({ ...params, bhtn_base_cap: x })}
                />
              </div>
            </div>

            <div className="lg-params-card">
              <h4 className="lg-params-card-title">
                Khấu trừ Thuế & Chuyên cần
              </h4>
              <div className="lg-params-fields">
                <NumField
                  label="Giảm trừ gia cảnh bản thân"
                  suffix="đ"
                  v={params.deduction_self}
                  on={(x) => setParams({ ...params, deduction_self: x })}
                />
                <NumField
                  label="Giảm trừ người phụ thuộc"
                  suffix="đ"
                  v={params.deduction_dependent}
                  on={(x) => setParams({ ...params, deduction_dependent: x })}
                />
                <NumField
                  label="Mức thưởng chuyên cần mặc định"
                  suffix="đ"
                  v={params.chuyen_can_default}
                  on={(x) => setParams({ ...params, chuyen_can_default: x })}
                />
              </div>
            </div>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>
            {busy ? "Đang lưu…" : "Lưu thay đổi"}
          </button>
        </footer>
      </div>
    </div>
  );
}

// --- Phiếu lương 2 cột (Thu | Trừ) — dùng chung cho self-service + In của HCNS ---------------

const pctFmt = (r: number) => (r * 100).toLocaleString("vi-VN", { maximumFractionDigits: 2 });

function PayslipCard({ line: l, period, params }: {
  line: PayrollLine;
  period: PayrollPeriod;
  params: PayrollParams | null;   // để tách BHXH/BHYT/BHTN; null (thiếu quyền) → hiện gộp
}) {
  const capY = params && params.bh_base_cap > 0 ? Math.min(l.insurance_base, params.bh_base_cap) : l.insurance_base;
  const capTN = params && params.bhtn_base_cap > 0 ? Math.min(l.insurance_base, params.bhtn_base_cap) : l.insurance_base;

  const income = ([
    ["Lương theo công", l.luong_cong],
    ["Phụ cấp", l.allowance],
    ["Chuyên cần", l.chuyen_can],
    ["Lương khoán / sản lượng", l.khoan],
    ["Tăng ca", l.ot_pay],
    ["Phụ cấp ca đêm", l.night_pay],
    ["Phép năm", l.phep_nam],
    ["Thưởng 5S", l.thuong_5s],
    ["Thưởng doanh số", l.thuong_doanh_so],
    ["Thưởng thành tích", l.thuong_thanh_tich],
    ["Trả đồng phục", l.tra_dong_phuc],
    ["Thưởng khác", l.other_bonus],
  ] as [string, number][]);
  const incomeTotal = income.reduce((s, [, v]) => s + v, 0);

  const deduct = ([
    ...(params
      ? ([
          [`BHXH ${pctFmt(params.bhxh_rate)}%`, capY * params.bhxh_rate],
          [`BHYT ${pctFmt(params.bhyt_rate)}%`, capY * params.bhyt_rate],
          [`BHTN ${pctFmt(params.bhtn_rate)}%`, capTN * params.bhtn_rate],
        ] as [string, number][])
      : ([["BHXH / BHYT / BHTN", l.bhxh]] as [string, number][])),
    [`Công đoàn${params && params.cong_doan_rate ? ` ${pctFmt(params.cong_doan_rate)}%` : ""}`, l.cong_doan],
    ["Thuế TNCN", l.pit],
    ["Đi trễ / nghỉ KP", l.di_tre],
    ["Điện thoại vượt trội", l.dt_vuot_troi],
    ["Phạt biên bản", l.phat_bien_ban],
    ["Đồng phục / phạt 5S", l.phat_5s_dong_phuc],
    ["Giảm trừ khác", l.vi_pham],
    ["Tạm ứng đã nhận", l.advance_total],
  ] as [string, number][]);
  const deductTotal = deduct.reduce((s, [, v]) => s + v, 0);

  return (
    <div className="lg-payslip2 lg-payslip-print">
      <div className="lg-payslip2__head">
        <div>
          <div className="lg-payslip2__title">PHIẾU LƯƠNG</div>
          <div className="lg-payslip2__who">{l.employee_name} <span className="ns__code">{l.employee_code}</span></div>
          <div className="cc-card__hint">{l.department_name ?? "—"} · Tháng {String(period.month).padStart(2, "0")}/{period.year}</div>
        </div>
        <div className="lg-payslip2__meta">
          <div>NC chuẩn: <b>{l.standard_cong}</b> · Ngày công: <b>{l.actual_cong}</b></div>
          <div>Giờ tăng ca: <b>{(l.ot_minutes / 60).toFixed(1)}h</b> · Mức đóng BH: <b>{money(l.insurance_base)}</b></div>
          <span className={`ns-badge ${period.status !== "draft" ? "ns-badge--ok" : "ns-badge--muted"}`}>
            {period.status === "paid" ? "Đã chi" : period.status === "locked" ? "Đã chốt" : "Tạm tính"}
          </span>
        </div>
      </div>
      <div className="lg-payslip2__cols">
        <table className="lg-payslip2__tbl">
          <thead><tr><th>Các khoản THU</th><th className="lg-num">Số tiền</th></tr></thead>
          <tbody>
            {income.map(([lbl, v]) => <tr key={lbl}><td>{lbl}</td><td className="lg-num">{v ? money(v) : "—"}</td></tr>)}
            <tr className="lg-payslip2__sub"><td>TỔNG THU</td><td className="lg-num">{money(incomeTotal)}</td></tr>
          </tbody>
        </table>
        <table className="lg-payslip2__tbl">
          <thead><tr><th>Các khoản TRỪ</th><th className="lg-num">Số tiền</th></tr></thead>
          <tbody>
            {deduct.map(([lbl, v]) => <tr key={lbl}><td>{lbl}</td><td className="lg-num">{v ? money(v) : "—"}</td></tr>)}
            <tr className="lg-payslip2__sub"><td>TỔNG TRỪ</td><td className="lg-num">{money(deductTotal)}</td></tr>
          </tbody>
        </table>
      </div>
      <div className="lg-payslip2__net"><span>THỰC NHẬN</span><span>{money(l.net_pay)}đ</span></div>
      <div className="lg-payslip2__sign">
        <div>Người lập phiếu</div>
        <div>Người nhận tiền<br /><span className="cc-card__hint">(ký, ghi rõ họ tên)</span></div>
      </div>
    </div>
  );
}

// --- Tab: Tạm ứng của tôi (self-service — nhân viên tự đề nghị) --------------

function TamUngCuaToiTab({ token, eventTick }: { token: string; eventTick?: number }) {
  const [data, setData] = useState<{ has_employee: boolean; items: SalaryAdvance[] } | null>(null);
  const [adding, setAdding] = useState(false);

  const load = useCallback(() => {
    api.luong
      .myAdvances(token)
      .then(setData)
      .catch(() => setData({ has_employee: false, items: [] }));
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

  if (!data)
    return (
      <p className="lg-payslip-empty-desc" style={{ textAlign: "center", marginTop: 24 }}>
        Đang tải…
      </p>
    );
  if (!data.has_employee)
    return (
      <div className="lg-table-empty-state">
        <div className="lg-table-empty-icon"><Wallet size={20} /></div>
        <span className="lg-table-empty-title">Tài khoản chưa gắn hồ sơ nhân sự</span>
        <span className="lg-table-empty-desc">
          Liên hệ HCNS để liên kết tài khoản với hồ sơ, sau đó mới lập đề nghị tạm ứng được.
        </span>
      </div>
    );
  return (
    <div>
      <div className="cc-toolbar lg-toolbar">
        <button className="btn btn--primary" onClick={() => setAdding(true)}>
          + Đề nghị tạm ứng
        </button>
        <span className="cc-card__hint">Đề nghị gửi tới kế toán duyệt; bấm “In phiếu” để ký &amp; nộp.</span>
      </div>
      {data.items.length === 0 ? (
        <div className="lg-table-empty-state">
          <div className="lg-table-empty-icon"><Wallet size={20} /></div>
          <span className="lg-table-empty-title">Chưa có đề nghị tạm ứng</span>
          <span className="lg-table-empty-desc">Nhấp “+ Đề nghị tạm ứng” để lập phiếu gửi kế toán.</span>
        </div>
      ) : (
        <div className="lg-emp-table-wrapper">
          <table className="ns__table">
            <thead>
              <tr>
                <th>Mã</th>
                <th>Kỳ</th>
                <th>Ngày ứng</th>
                <th className="lg-num">Số tiền</th>
                <th>Lý do</th>
                <th>Trạng thái</th>
                <th>Hành động</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((a) => {
                const [label, cls] = STATUS[a.status] ?? [a.status, "ns-badge--muted"];
                return (
                  <tr key={a.id}>
                    <td className="font-mono">{a.code ?? "—"}</td>
                    <td>{String(a.period_month).padStart(2, "0")}/{a.period_year}</td>
                    <td>{a.advance_date}</td>
                    <td className="lg-num font-mono">{money(a.amount)}đ</td>
                    <td>{a.reason ?? "—"}</td>
                    <td><span className={`ns-badge ${cls}`}>{label}</span></td>
                    <td className="cc-rowact">
                      <button
                        className="btn btn--ghost"
                        onClick={() => printAdvanceRequest(advPrintData(a))}
                      >
                        🖨 In phiếu
                      </button>
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
          onClose={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            load();
          }}
        />
      )}
    </div>
  );
}

function MyAdvanceModal({
  token,
  onClose,
  onSaved,
}: {
  token: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [ym, setYm] = useState(curYm());
  const [amount, setAmount] = useState(0);
  const [dateStr, setDateStr] = useState(() => new Date().toISOString().slice(0, 10));
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    if (amount <= 0) {
      setErr("Nhập số tiền > 0.");
      return;
    }
    const [year, month] = ym.split("-").map(Number);
    setBusy(true);
    setErr(null);
    try {
      await api.luong.createMyAdvance(token, {
        period_year: year,
        period_month: month,
        advance_date: dateStr,
        amount,
        reason: reason || null,
      });
      onSaved();
    } catch (e) {
      setErr(errText(e));
      setBusy(false);
    }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>Đề nghị tạm ứng</h2>
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          <div className="ns-grid">
            <label className="ns-field">
              <span className="ns-field__label">Kỳ lương</span>
              <input type="month" value={ym} onChange={(e) => setYm(e.target.value)} />
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Ngày ứng</span>
              <input type="date" value={dateStr} onChange={(e) => setDateStr(e.target.value)} />
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Số tiền *</span>
              <input type="number" min={0} value={amount} onChange={(e) => setAmount(Number(e.target.value))} />
            </label>
          </div>
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Lý do</span>
            <input value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>Hủy</button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>
            {busy ? "Đang gửi…" : "Gửi đề nghị"}
          </button>
        </footer>
      </div>
    </div>
  );
}

// --- Tab: Phiếu lương của tôi -----------------------------------------------

function PhieuLuongTab({ token }: { token: string }) {
  const [data, setData] = useState<Awaited<
    ReturnType<typeof api.luong.myPayslip>
  > | null>(null);
  const [params, setParams] = useState<PayrollParams | null>(null);
  useEffect(() => {
    api.luong
      .myPayslip(token)
      .then(setData)
      .catch(() => setData(null));
    // Tỷ lệ BH để tách BHXH/BHYT/BHTN — NV không có quyền lương thì catch → hiện gộp.
    api.luong.getParams(token).then(setParams).catch(() => setParams(null));
  }, [token]);

  if (!data)
    return (
      <div className="lg-payslip-empty-container">
        <div className="lg-payslip-empty-card">
          <p className="lg-payslip-empty-desc">Đang tải dữ liệu...</p>
        </div>
      </div>
    );
  if (!data.has_employee) {
    return (
      <div className="lg-payslip-empty-container">
        <div className="lg-payslip-empty-card">
          <div className="lg-payslip-empty-icon lg-payslip-empty-icon--warn">
            <AlertTriangle size={24} />
          </div>
          <h3 className="lg-payslip-empty-title">Tài khoản chưa gắn hồ sơ</h3>
          <p className="lg-payslip-empty-desc">
            Tài khoản của bạn chưa được liên kết với bất kỳ hồ sơ nhân viên nào.
            Vui lòng liên hệ bộ phận HCNS để được thiết lập.
          </p>
        </div>
      </div>
    );
  }
  const l = data.line;
  if (!l || !data.period) {
    return (
      <div className="lg-payslip-empty-container">
        <div className="lg-payslip-empty-card">
          <div className="lg-payslip-empty-icon">
            <FileText size={24} />
          </div>
          <h3 className="lg-payslip-empty-title">Chưa có phiếu lương</h3>
          <p className="lg-payslip-empty-desc">
            Không tìm thấy dữ liệu phiếu lương của bạn cho tháng này. Phiếu
            lương sẽ hiển thị sau khi bộ phận HCNS hoàn tất việc chốt bảng
            lương.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="lg-payslip">
      <div className="lg-payslip-noprint" style={{ textAlign: "center", marginBottom: 8 }}>
        <button className="btn btn--ghost" onClick={() => window.print()}>🖨 In phiếu</button>
      </div>
      <PayslipCard line={l} period={data.period} params={params} />
    </div>
  );
}
