// Lương (module `luong`, Phase 1 — lương thời gian). 5 tab:
//   • Bảng lương tháng — Tạo → soát ô vàng → Chốt → xuất Excel + file chuyển khoản.
//   • Lương nhân viên — khai báo (nhóm/bậc + mức) & điều chỉnh (lịch sử).
//   • Tạm ứng — ghi nhiều lần → duyệt → tự trừ.
//   • Cấu hình lương — 3 tab con: bậc lương & KPI · cơ chế theo bộ phận · phụ cấp & bảo hiểm.
//   • Phiếu lương của tôi — self-service.
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
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
} from "lucide-react";
import {
  api,
  type EmployeeRow,
  type EmployeeSalary,
  type PayrollLine,
  type PayrollParams,
  type PayrollPeriod,
  type MyAdvances,
  type SalaryAdvance,
  type SalaryPreview,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { fmtDateTime } from "../utils/format";
import { printAdvanceRequest } from "../utils/printAdvanceRequest";
import { CauHinhLuongTab } from "./CauHinhLuongTab";
import { DiscardChangesDialog } from "../components/DiscardChangesDialog";
import { KhoanRatesEditor } from "../components/KhoanRatesEditor";
import "./nhan-su.css";
import "./luong.css";

type Tab = "bang" | "nhanvien" | "khoan" | "tamung" | "cauhinh" | "phieu" | "tamung-me";

function money(n: number | null | undefined): string {
  if (n == null) return "0";
  return Math.round(n).toLocaleString("vi-VN");
}
function fmtYmd(value: string | null | undefined): string {
  if (!value) return "Đến nay";
  const [y, m, d] = value.split("-");
  return y && m && d ? `${d}/${m}/${y}` : value;
}
function curYm(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
// Hôm nay dạng YYYY-MM-DD, dựng từ giờ ĐỊA PHƯƠNG (không dùng toISOString để tránh
// lệch 1 ngày khi ở múi giờ VN lúc rạng sáng).
function todayYmd(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function errText(e: unknown): string {
  return e instanceof Error ? e.message : "Có lỗi xảy ra.";
}

export function LuongPage({
  focusEmployeeId,
  eventTick,
  openTab,
}: {
  focusEmployeeId?: number;
  /** Tăng mỗi sự kiện real-time (SSE) → tab Tạm ứng đang mở tự refetch, không cần đổi màn. */
  eventTick?: number;
  /** Liên thông từ màn Phòng ban ("Sửa ở Cấu hình lương") → mở thẳng tab cấu hình. */
  openTab?: "cauhinh";
}) {
  const { token } = useAuth();
  const can = useCan();
  const canManage = can("luong", "update");
  // Cấu hình lương là dữ liệu nhạy cảm: quyền đọc module không đủ.
  // Người có quyền sửa luôn được xem để tránh ma trận quyền cũ khóa nhầm quản trị viên.
  const canReadConfig = can("luong", "view_salary") || canManage;
  const [tab, setTab] = useState<Tab>(
    canManage ? "bang" : canReadConfig ? "cauhinh" : "phieu",
  );
  // Cấu hình lương đang có thay đổi chưa lưu → chặn rời tab (S5).
  const [cfgDirty, setCfgDirty] = useState(false);
  const [pendingTab, setPendingTab] = useState<Tab | null>(null);
  function go(next: Tab) {
    if (next === tab) return;
    if (tab === "cauhinh" && cfgDirty) setPendingTab(next);
    else setTab(next);
  }

  // Liên thông từ Hồ sơ nhân sự → mở tab "Lương nhân viên" tại đúng NV.
  useEffect(() => {
    if (focusEmployeeId && canManage) setTab("nhanvien");
  }, [focusEmployeeId, canManage]);
  useEffect(() => {
    if (openTab === "cauhinh" && canReadConfig) setTab("cauhinh");
  }, [openTab, canReadConfig]);

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
            onClick={() => go("bang")}
          >
            Bảng lương tháng
          </button>
        )}
        {canManage && (
          <button
            className={tab === "nhanvien" ? "is-active" : ""}
            onClick={() => go("nhanvien")}
          >
            Lương nhân viên
          </button>
        )}
        {canManage && (
          <button
            className={tab === "khoan" ? "is-active" : ""}
            onClick={() => go("khoan")}
          >
            Lương khoán
          </button>
        )}
        {canManage && (
          <button
            className={tab === "tamung" ? "is-active" : ""}
            onClick={() => go("tamung")}
          >
            Tạm ứng
          </button>
        )}
        {canReadConfig && (
          <button
            className={tab === "cauhinh" ? "is-active" : ""}
            onClick={() => go("cauhinh")}
          >
            Cấu hình lương
          </button>
        )}
        <button
          className={tab === "phieu" ? "is-active" : ""}
          onClick={() => go("phieu")}
        >
          Phiếu lương của tôi
        </button>
        <button
          className={tab === "tamung-me" ? "is-active" : ""}
          onClick={() => go("tamung-me")}
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
      {tab === "cauhinh" && canReadConfig && (
        <CauHinhLuongTab token={token!} readOnly={!canManage} onDirtyChange={setCfgDirty} />
      )}
      {tab === "phieu" && <PhieuLuongTab token={token!} />}
      {tab === "tamung-me" && <TamUngCuaToiTab token={token!} eventTick={eventTick} />}

      <DiscardChangesDialog
        open={pendingTab !== null}
        message="Bạn có thay đổi chưa lưu ở Cấu hình lương. Rời đi mà không lưu?"
        onDiscard={() => {
          setCfgDirty(false);
          if (pendingTab) setTab(pendingTab);
          setPendingTab(null);
        }}
        onKeepEditing={() => setPendingTab(null)}
      />
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
    (s, l) =>
      s + (l.vi_pham ?? 0) + (l.bhxh ?? 0) + (l.advance_total ?? 0) + (l.luong_dot_1_total ?? 0),
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
                    <span className="lg-source-name">Thang bậc lương của tổ</span>
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
                    <span className="lg-param-name">Công chuẩn / tháng</span>
                    <span className="lg-param-val">
                      Tự tính theo Lịch &amp; Ngày lễ
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
                <th className="lg-num">Đợt 1 / Tạm ứng</th>
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
                    title={[
                      l.night_days ? `${l.night_days} ngày ca đêm` : "",
                      l.night_pay ? `phụ cấp ca (tay) ${money(l.night_pay)}` : "",
                      l.night_premium_pay ? `premium giờ×hệ số ${money(l.night_premium_pay)}` : "",
                    ].filter(Boolean).join(" · ")}
                  >
                    {(l.night_pay || l.night_premium_pay)
                      ? money((l.night_pay ?? 0) + (l.night_premium_pay ?? 0)) : "—"}
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
                  <td className={`lg-num ${(l.advance_total || l.luong_dot_1_total) ? "lg-minus" : ""}`}>
                    {l.luong_dot_1_total ? (
                      <div title="Thanh toán lương đợt 1">−{money(l.luong_dot_1_total)}</div>
                    ) : null}
                    {l.advance_total ? (
                      <div title="Tạm ứng đã nhận">−{money(l.advance_total)}</div>
                    ) : null}
                    {!l.advance_total && !l.luong_dot_1_total ? "—" : null}
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
              <PayslipCard line={printing} period={period} />
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
  // % đạt KPI của tháng → tiền = % × mức TRẦN KPI khai ở Cấu hình lương (tab Cơ chế bộ phận).
  const [kpi, setKpi] = useState(line.kpi_percent);
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
  // Ô "Đi trễ": mặc định TỰ ĐỘNG từ chấm công. `di_tre_manual` = HCNS đã ghi đè tay.
  const [diTreManual, setDiTreManual] = useState(line.di_tre_manual);

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      // TNCN LUÔN tự tính theo Biểu thuế lũy tiến — KHÔNG gửi `pit`; ép `pit_manual:false`
      // để backend tính lại TNCN theo thu nhập chịu thuế mới (không cho sửa tay).
      const { di_tre, ...restDetail } = detail;
      const input = {
        vi_pham: viPham, other_bonus: bonus, kpi_percent: kpi, pit_manual: false,
        note: note || null, ...restDetail,
        // Đi trễ: chỉ gửi số TAY khi HCNS chủ động sửa (khóa auto); bỏ về tự động → gửi cờ false
        // (backend tính lại từ chấm công). Auto không đổi → không gửi gì, giữ nguyên số auto.
        ...(diTreManual
          ? { di_tre }
          : line.di_tre_manual
            ? { di_tre_manual: false }
            : {}),
      };
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
  // "Đi trễ" render RIÊNG (auto/sửa tay); các ô phạt còn lại nhập tay bình thường.
  const penaltyFields: [keyof typeof detail, string][] = [
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
            <label className="ns-field">
              <span className="ns-field__label">KPI (%)</span>
              <input
                type="number"
                min={0}
                max={200}
                step={5}
                value={kpi}
                onChange={(e) => setKpi(Number(e.target.value))}
              />
              <span className="cc-card__hint">
                % đạt của tháng × mức trần KPI của bộ phận. Bộ phận tắt KPI → luôn 0. Thưởng
                KPI hiện tại: <b>{money(line.kpi_bonus)}đ</b>
              </span>
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
            <label className="ns-field">
              <span className="ns-field__label">
                Đi trễ / nghỉ KP{" "}
                <span className={`ns-badge ${diTreManual ? "ns-badge--muted" : "ns-badge--ok"}`}>
                  {diTreManual ? "đã sửa tay" : "tự động"}
                </span>
              </span>
              <input
                type="number"
                min={0}
                value={detail.di_tre}
                readOnly={!diTreManual}
                onChange={(e) => setD("di_tre", Number(e.target.value))}
              />
              <span className="cc-card__hint">
                {diTreManual ? (
                  <>
                    Đang dùng số nhập tay.{" "}
                    <button type="button" className="lg-linkbtn" onClick={() => setDiTreManual(false)}>
                      ↩ Về tự động từ chấm công
                    </button>
                  </>
                ) : (
                  <>
                    Tự tính từ chấm công (bảng phạt × số phút trễ/về sớm KHÔNG phép mỗi ngày).{" "}
                    <button type="button" className="lg-linkbtn" onClick={() => setDiTreManual(true)}>
                      ✎ Sửa tay
                    </button>
                  </>
                )}
              </span>
            </label>
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

/** Phụ cấp KHAI TAY của NV — MỘT ô gộp mọi loại (số cố định, engine cộng phẳng mọi tháng).
 *  Hoist ra ngoài JSX (có type hẳn hoi) thay vì cast inline trong render. */
type PhuCapKey = "allowance";
const PHU_CAP_FIELDS: [PhuCapKey, string, string][] = [
  ["allowance", "Các khoản phụ cấp", "Xăng xe · điện thoại · thâm niên · ca · chuyên môn… gộp thành một số cố định."],
];

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
  // form khai/điều chỉnh lương — hiệu lực LUÔN LÀ HÔM NAY (không cho chọn ngày):
  // sửa hôm nay thì áp dụng từ hôm nay, và mốc vừa lưu là mốc mới nhất nên màn không "nhảy" về số cũ.
  // C2: mức HỢP ĐỒNG của chính NV — gõ riêng 2 ô, không tự tách từ một số tổng.
  const [luongViTri, setLuongViTri] = useState(0);
  const [luongTrachNhiem, setLuongTrachNhiem] = useState(0);
  // "Lương trả 1 lần" (đợt 1): mức trả trong MỘT lần — chỉ là số điền sẵn khi lập phiếu
  // "thanh toán lương đợt 1". Khai ở đây, muốn trả thì sang tab Tạm ứng lập phiếu + duyệt.
  const [luongDot1, setLuongDot1] = useState(0);
  // 3 khoản PHỤ CẤP KHAI TAY của NV — số cố định, cộng phẳng mọi tháng, hệ thống KHÔNG tự
  // tính gì. Gõ một lần, khi nào đổi thì sửa lại.
  const [allowance, setAllowance] = useState(0); // phụ cấp KHÁC (gộp)
  const [chuyenCan, setChuyenCan] = useState(0); // chuyên cần riêng NV
  // BH đóng ở nơi khác → công ty không trừ BHXH/BHYT/BHTN của NV, chỉ chịu TNLĐ-BNN.
  const [insuranceElsewhere, setInsuranceElsewhere] = useState(false);
  // Đoàn viên công đoàn → mới bị trừ đoàn phí công đoàn (mặc định không).
  const [unionMember, setUnionMember] = useState(false);
  const [params, setParams] = useState<PayrollParams | null>(null); // tỷ lệ BHXH/BHYT/BHTN + trần

  const reload = useCallback(async () => {
    const [prev, hist] = await Promise.all([
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
    // Điền sẵn theo bản lương mới nhất (để SỬA thay vì khai lại từ đầu).
    const latest = hist.items.length
      ? [...hist.items].sort((a, b) =>
          b.effective_from.localeCompare(a.effective_from),
        )[0]
      : null;
    if (latest) {
      setAllowance(latest.allowance ?? 0);
      setChuyenCan(latest.chuyen_can ?? 0);
      setLuongDot1(latest.luong_dot_1 ?? 0);
      setInsuranceElsewhere(!!latest.insurance_elsewhere);
      setUnionMember(!!latest.union_member);
      // Bản ghi cũ chưa tách 2 ô → dồn base_amount vào lương cơ bản để sửa tiếp, không mất số.
      const vt = latest.luong_vi_tri ?? 0;
      const tn = latest.luong_trach_nhiem ?? 0;
      if (vt > 0 || tn > 0) {
        setLuongViTri(vt);
        setLuongTrachNhiem(tn);
      } else {
        setLuongViTri(latest.base_amount ?? 0);
        setLuongTrachNhiem(0);
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
    setBusy(true);
    setErr(null);
    setOk(null);
    try {
      const eff = todayYmd(); // hiệu lực = hôm nay
      await api.luong.setSalary(token, emp.id, {
        effective_from: eff,
        amount_mode: "manual",
        luong_vi_tri: luongViTri,
        luong_trach_nhiem: luongTrachNhiem,
        luong_dot_1: luongDot1,
        allowance,
        chuyen_can: chuyenCan,
        insurance_elsewhere: insuranceElsewhere,
        union_member: unionMember,
      });
      setOk("Đã lưu lương (hiệu lực từ hôm nay " + fmtYmd(eff) + ").");
      reload();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }

  // Tiền BHXH/BHYT/BHTN nhân viên đóng — theo TỶ LỆ đã cấu hình + áp trần RIÊNG đúng như engine
  // (_compute): mức đóng BH = LƯƠNG CƠ BẢN (chỉ vị trí), KHÔNG gồm trách nhiệm.
  const salaryBase = luongViTri + luongTrachNhiem; // mức nền: prorate công + gốc tính tăng ca
  const bhBase = luongViTri;                        // đóng BH trên lương cơ bản (vị trí)

  const phuCap: Record<PhuCapKey, number> = { allowance };
  const setPhuCap: Record<PhuCapKey, (v: number) => void> = { allowance: setAllowance };
  const phuCapTotal = allowance;
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
                {preview.source === "manual" || preview.source === "employee"
                  ? "mức hợp đồng riêng"
                  : preview.source === "dept_row"
                    ? "theo bảng lương tổ (dữ liệu cũ)"
                    : preview.source === "rule"
                      ? "theo quy tắc"
                      : "chưa có"}
              </span>
              {" · "}phụ cấp {money(preview.allowance)} · đóng BH trên{" "}
              {money(preview.insurance_base)}
            </div>
          )}

          <h4 className="ns-section__title">Khai / Điều chỉnh lương</h4>
          <p className="cc-note">
            Mức lương là HỢP ĐỒNG của riêng người này — gõ thẳng 2 ô dưới. BHXH/BHYT/BHTN đóng
            trên lương cơ bản. Khi lưu, mức mới <b>áp dụng từ hôm nay</b> và mốc cũ được giữ trong
            Lịch sử điều chỉnh.
          </p>
          <div className="ns-grid" style={{ marginTop: 10 }}>
            <label className="ns-field">
              <span className="ns-field__label">Lương cơ bản (đóng BH)</span>
              <input
                type="number"
                min={0}
                step={100000}
                value={luongViTri}
                onChange={(e) => setLuongViTri(Number(e.target.value))}
              />
              <span className="cc-card__hint">BHXH/BHYT/BHTN đóng trên số này.</span>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Lương trách nhiệm</span>
              <input
                type="number"
                min={0}
                step={100000}
                value={luongTrachNhiem}
                onChange={(e) => setLuongTrachNhiem(Number(e.target.value))}
              />
              <span className="cc-card__hint">
                Mức nền = vị trí + trách nhiệm: <b>{money(salaryBase)}đ</b>. Tăng ca tính trên
                số này.
              </span>
            </label>
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
              <span className="cc-card__hint">
                Để 0 = dùng mức chuyên cần của tổ (Cấu hình lương → Cơ chế lương theo bộ phận).
              </span>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Lương trả 1 lần (đợt 1)</span>
              <input
                type="number"
                min={0}
                step={100000}
                value={luongDot1}
                onChange={(e) => setLuongDot1(Number(e.target.value))}
              />
              <span className="cc-card__hint">
                Mức trả trong MỘT lần. Đây chỉ là số điền sẵn — muốn trả đợt 1 thì sang tab
                <b> Tạm ứng</b> bấm <b>“+ Phiếu lương đợt 1”</b>, duyệt xong mới trừ vào lương.
              </span>
            </label>
          </div>

          {/* 3 khoản phụ cấp KHAI TAY — hệ thống không tính toán gì, cộng phẳng. */}
          <h4 className="ns-section__title" style={{ marginTop: 16 }}>
            Phụ cấp hằng tháng (khai tay)
          </h4>
          <p className="cc-note">
            Gõ một lần, tháng nào cũng cộng đúng số này. Khi nào đổi thì sửa lại. Ba khoản cộng
            phẳng vào thu nhập, không chia theo ngày công và không vào gốc tính tăng ca.
          </p>
          <div className="ns-grid" style={{ marginTop: 10 }}>
            {PHU_CAP_FIELDS.map(([key, label, hint]) => (
              <label className="ns-field" key={key}>
                <span className="ns-field__label">{label}</span>
                <input
                  type="number"
                  min={0}
                  step={100000}
                  value={phuCap[key]}
                  onChange={(e) => setPhuCap[key](Number(e.target.value))}
                />
                <span className="cc-card__hint">{hint}</span>
              </label>
            ))}
          </div>
          <p className="cc-card__hint">
            Tổng phụ cấp mỗi tháng: <b>{money(phuCapTotal)}đ</b>
          </p>

          <label className="ns-check" style={{ marginTop: 6 }}>
            <input
              type="checkbox"
              checked={insuranceElsewhere}
              onChange={(e) => setInsuranceElsewhere(e.target.checked)}
            />
            Bảo hiểm đóng ở nơi khác — công ty chỉ đóng TNLĐ-BNN
          </label>
          <p className="cc-card__hint">
            Tích khi NV đã được nơi khác đóng BHXH/BHYT/BHTN. Công ty không trừ 3 khoản này của họ.
          </p>

          <label className="ns-check" style={{ marginTop: 6 }}>
            <input
              type="checkbox"
              checked={unionMember}
              onChange={(e) => setUnionMember(e.target.checked)}
            />
            Đoàn viên công đoàn — có trừ đoàn phí công đoàn
          </label>
          <p className="cc-card__hint">
            Chỉ đoàn viên mới bị trừ đoàn phí công đoàn (theo tỷ lệ ở Cấu hình lương). Không tích = không trừ.
          </p>

          <div className="ns-grid" style={{ marginTop: 12 }}>
            <div className="ns-field" style={{ alignItems: "flex-end", gap: 6 }}>
              {ok && <span style={{ color: "#2e7d32", fontSize: 13, fontWeight: 600 }}>✓ {ok}</span>}
              {err && <span style={{ color: "#c62828", fontSize: 13, fontWeight: 600 }}>⚠ {err}</span>}
              <button
                className="btn btn--primary"
                onClick={saveSalary}
                disabled={busy}
              >
                {busy ? "Đang lưu…" : "Lưu điều chỉnh"}
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
              ) : insuranceElsewhere ? (
                <>
                  NV có <b>BH đóng ở nơi khác</b> — công ty KHÔNG trừ BHXH/BHYT/BHTN của NV.
                  <br />→ Công ty chỉ đóng <b>TNLĐ-BNN</b> {pctOf(params.tnld_bnn_rate)}% ={" "}
                  <b>{money(bhBase * params.tnld_bnn_rate)}đ</b> (chi phí công ty, không trừ vào lương NV).
                </>
              ) : (
                <>
                  Đóng BH trên lương cơ bản <b>{money(bhBase)}đ</b>, nhân viên đóng gồm:
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
          <div className="ns__tablewrap" style={{ overflowX: "auto" }}>
            <table className="ns__table">
              <thead>
                <tr>
                  <th>Trạng thái</th>
                  <th>Thời điểm sửa</th>
                  <th>Người sửa</th>
                  <th>Hiệu lực từ</th>
                  <th className="lg-num">Vị trí</th>
                  <th className="lg-num">Trách nhiệm</th>
                  <th className="lg-num">Mức nền</th>
                  <th className="lg-num">Phụ cấp</th>
                  <th>Ghi chú</th>
                </tr>
              </thead>
              <tbody>
                {history.map((s) => {
                  const vt = s.luong_vi_tri ?? 0;
                  const tn = s.luong_trach_nhiem ?? 0;
                  const nen = vt + tn > 0 ? vt + tn : (s.base_amount ?? 0);
                  return (
                    <tr key={s.id}>
                      <td>
                        {s.is_current ? (
                          <span className="ns-badge ns-badge--ok">Đang áp dụng</span>
                        ) : s.effective_to == null ? (
                          <span className="ns-badge ns-badge--muted">Sắp áp dụng</span>
                        ) : (
                          <span className="ns-badge ns-badge--muted">Đã thay</span>
                        )}
                      </td>
                      <td>{fmtDateTime(s.created_at)}</td>
                      <td>{s.actor_name ?? "—"}</td>
                      <td>{fmtYmd(s.effective_from)}</td>
                      <td className="lg-num">{vt ? money(vt) : "—"}</td>
                      <td className="lg-num">{tn ? money(tn) : "—"}</td>
                      <td className="lg-num">
                        <b>{money(nen)}</b>
                      </td>
                      <td className="lg-num">{money(s.allowance)}</td>
                      <td>{s.note ?? "—"}</td>
                    </tr>
                  );
                })}
                {history.length === 0 && (
                  <tr>
                    <td colSpan={9} className="ns__empty">
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
  return <KhoanRatesEditor token={token} />;
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
    kind: a.kind,
  };
}

function TamUngTab({ token, eventTick }: { token: string; eventTick?: number }) {
  const [ym, setYm] = useState(curYm);
  const [items, setItems] = useState<SalaryAdvance[]>([]);
  const [emps, setEmps] = useState<EmployeeRow[]>([]);
  const [adding, setAdding] = useState<null | "tam_ung" | "luong_dot_1">(null);
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
          <input
            type="month"
            value={ym}
            onChange={(e) => setYm(e.target.value)}
          />
        </div>
        <button className="btn btn--primary" onClick={() => setAdding("tam_ung")}>
          + Thêm ứng
        </button>
        <button className="btn btn--ghost" onClick={() => setAdding("luong_dot_1")}>
          + Phiếu lương đợt 1
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
                <th>Loại</th>
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
                const [kLabel, kCls] = KIND[a.kind] ?? KIND.tam_ung;
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
          kind={adding}
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

function AddAdvanceModal({
  token,
  emps,
  year,
  month,
  kind,
  onClose,
  onSaved,
}: {
  token: string;
  emps: EmployeeRow[];
  year: number;
  month: number;
  kind: "tam_ung" | "luong_dot_1";
  onClose: () => void;
  onSaved: () => void;
}) {
  const isDot1 = kind === "luong_dot_1";
  const [empId, setEmpId] = useState<number | "">("");
  const [amount, setAmount] = useState(0);
  const [dot1Profile, setDot1Profile] = useState<number | null>(null); // mức đợt 1 khai ở hồ sơ
  const [dateStr, setDateStr] = useState(() =>
    new Date().toISOString().slice(0, 10),
  );
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Phiếu đợt 1: chọn NV xong tự điền sẵn số tiền = "Lương trả 1 lần" trong hồ sơ (cho sửa).
  useEffect(() => {
    if (!isDot1 || empId === "") {
      setDot1Profile(null);
      return;
    }
    let alive = true;
    api.luong
      .salaries(token, Number(empId))
      .then((r) => {
        if (!alive) return;
        const latest = r.items.length
          ? [...r.items].sort((a, b) => b.effective_from.localeCompare(a.effective_from))[0]
          : null;
        const d1 = latest?.luong_dot_1 ?? 0;
        setDot1Profile(d1);
        setAmount(d1);
      })
      .catch(() => {
        if (alive) setDot1Profile(null);
      });
    return () => {
      alive = false;
    };
  }, [isDot1, empId, token]);

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
        kind,
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
            {isDot1 ? "Phiếu lương đợt 1" : "Thêm tạm ứng"} — {String(month).padStart(2, "0")}/{year}
          </h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          {isDot1 && (
            <p className="cc-note">
              Số tiền điền sẵn theo <b>“Lương trả 1 lần”</b> trong hồ sơ NV (sửa được). Duyệt phiếu
              xong mới trừ vào lương — hiện thành dòng <b>“Thanh toán lương đợt 1”</b> trên phiếu lương.
            </p>
          )}
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
              {isDot1 && empId !== "" && (
                <span className="cc-card__hint">
                  {dot1Profile && dot1Profile > 0
                    ? `Hồ sơ khai: ${money(dot1Profile)}đ`
                    : "Hồ sơ chưa khai 'Lương trả 1 lần' — nhập số tiền cần trả."}
                </span>
              )}
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

// --- Phiếu lương 2 cột (Thu | Trừ) — dùng chung cho self-service + In của HCNS ---------------

function PayslipCard({ line: l, period }: {
  line: PayrollLine;
  period: PayrollPeriod;
}) {
  // 3 khoản phụ cấp KHAI TAY — mỗi khoản một dòng. BẪY CỘNG ĐÔI: `l.allowance` là TỔNG của
  // đúng 2 số (thâm niên + khác) → KHÔNG cộng `allowance` vào tổng thu nữa. Phụ cấp CA
  // (`ca_pay`, chính là `night_pay`) là khoản RIÊNG, nằm NGOÀI `allowance`.
  // Dòng lương cũ: khác = allowance, thâm niên = 0 → vẫn hiện đúng, không mất tiền.
  const pcCa = l.ca_pay ?? l.night_pay;
  const pcThamNien = l.phu_cap_tham_nien ?? 0;
  const pcKhac = l.phu_cap_khac ?? l.allowance - pcThamNien;

  // Dòng phụ "TRONG ĐÓ" — chỉ để NV đối chiếu, TUYỆT ĐỐI KHÔNG cộng vào TỔNG THU: số này đã
  // nằm sẵn trong `luong_cong` (ngày nghỉ phép chỉ trả LƯƠNG VỊ TRÍ, không có lương trách
  // nhiệm). Cùng idiom `phu_cap_tham_nien ⊂ allowance`; cộng nhầm là SAI TIỀN LƯƠNG.
  // Key = nhãn dòng cha → dòng phụ render ngay dưới dòng đó và nằm NGOÀI `incomeTotal`.
  const luongNgayPhep = l.luong_ngay_phep ?? 0;
  const incomeSub: Record<string, [string, number]> = luongNgayPhep > 0
    ? { "Lương theo công": ["Trong đó: lương ngày phép (theo lương vị trí)", luongNgayPhep] }
    : {};

  const income = ([
    ["Lương theo công", l.luong_cong],
    ["Phụ cấp ca", pcCa],
    ["Phụ cấp ca đêm (giờ × hệ số)", l.night_premium_pay ?? 0],
    ["Phụ cấp thâm niên", pcThamNien],
    ["Phụ cấp khác", pcKhac],
    ["Chuyên cần", l.chuyen_can],
    ["Lương khoán / sản lượng", l.khoan],
    ["Tăng ca", l.ot_pay],
    // NV tự đối chiếu được: % đạt hiện ngay trên nhãn (chỉ khi có), tiền ở cột phải.
    [
      `Thưởng KPI${l.kpi_percent ? ` (${l.kpi_percent.toLocaleString("vi-VN", { maximumFractionDigits: 2 })}%)` : ""}`,
      l.kpi_bonus,
    ],
    ["Phép năm", l.phep_nam],
    ["Thưởng 5S", l.thuong_5s],
    ["Thưởng doanh số", l.thuong_doanh_so],
    ["Thưởng thành tích", l.thuong_thanh_tich],
    ["Trả đồng phục", l.tra_dong_phuc],
    ["Thưởng khác", l.other_bonus],
  ] as [string, number][]);
  const incomeTotal = income.reduce((s, [, v]) => s + v, 0);

  // BHXH/BHYT/BHTN: backend trả sẵn 3 dòng (nhãn đã kèm tỷ lệ) — AI XEM CŨNG THẤY, không phải đi xin
  // `GET /params` vốn đòi quyền cấu hình lương. Tổng 3 dòng luôn đúng bằng `l.bhxh` đã đóng băng.
  const deduct = ([
    ...((l.insurance_lines ?? []).map((r) => [r.label, r.amount]) as [string, number][]),
    ["Công đoàn", l.cong_doan],
    ["Thuế TNCN", l.pit],
    ["Đi trễ / nghỉ KP", l.di_tre],
    ["Điện thoại vượt trội", l.dt_vuot_troi],
    ["Phạt biên bản", l.phat_bien_ban],
    ["Đồng phục / phạt 5S", l.phat_5s_dong_phuc],
    ["Giảm trừ khác", l.vi_pham],
    // 2 dòng RIÊNG: đợt 1 (đã trả giữa tháng qua phiếu) và tạm ứng ad-hoc. Thực nhận = đợt 2.
    ["Thanh toán lương đợt 1", l.luong_dot_1_total ?? 0],
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
            {income.map(([lbl, v]) => {
              const sub = incomeSub[lbl];
              return (
                <Fragment key={lbl}>
                  <tr><td>{lbl}</td><td className="lg-num">{v ? money(v) : "—"}</td></tr>
                  {sub && (
                    <tr className="lg-payslip2__in">
                      <td>{sub[0]}</td><td className="lg-num">{money(sub[1])}</td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
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
        <button className="btn btn--primary" onClick={() => setAdding("tam_ung")}>
          + Đề nghị tạm ứng
        </button>
        <button className="btn btn--ghost" onClick={() => setAdding("luong_dot_1")}>
          + Xin lương đợt 1
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
                <th>Loại</th>
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
                const [kLabel, kCls] = KIND[a.kind] ?? KIND.tam_ung;
                return (
                  <tr key={a.id}>
                    <td className="font-mono">{a.code ?? "—"}</td>
                    <td><span className={`ns-badge ${kCls}`}>{kLabel}</span></td>
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
          kind={adding}
          dot1Prefill={data.luong_dot_1}
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

function MyAdvanceModal({
  token,
  kind,
  dot1Prefill,
  onClose,
  onSaved,
}: {
  token: string;
  kind: "tam_ung" | "luong_dot_1";
  dot1Prefill: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isDot1 = kind === "luong_dot_1";
  const [ym, setYm] = useState(curYm());
  // Phiếu đợt 1: điền sẵn theo "Lương trả 1 lần" trong hồ sơ (vẫn cho sửa).
  const [amount, setAmount] = useState(isDot1 ? dot1Prefill : 0);
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
        kind,
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
          <h2>{isDot1 ? "Xin thanh toán lương đợt 1" : "Đề nghị tạm ứng"}</h2>
          <button className="ns-modal__x" onClick={onClose}>×</button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          {isDot1 && (
            <p className="cc-note">
              Số tiền điền sẵn theo <b>“Lương trả 1 lần”</b> trong hồ sơ của bạn — sửa được. Kế toán
              duyệt xong mới trừ, hiện thành dòng <b>“Thanh toán lương đợt 1”</b> trên phiếu lương.
              {dot1Prefill <= 0 && <> Hồ sơ chưa khai mức này — nhập số bạn muốn ứng hoặc hỏi HCNS.</>}
            </p>
          )}
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
  useEffect(() => {
    // Không gọi `getParams` nữa: 3 dòng BHXH/BHYT/BHTN do backend trả kèm phiếu, nên nhân viên
    // KHÔNG cần quyền cấu hình lương (trước đây gọi rồi ăn 403 → phiếu rơi về dòng gộp).
    api.luong
      .myPayslip(token)
      .then(setData)
      .catch(() => setData(null));
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
      <PayslipCard line={l} period={data.period} />
    </div>
  );
}
