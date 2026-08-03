// Lương (module `luong`, Phase 1 — lương thời gian). 5 tab:
//   • Bảng lương tháng — Tạo → soát ô vàng → Chốt → xuất Excel + file chuyển khoản.
//   • Lương nhân viên — khai báo (nhóm/bậc + mức) & điều chỉnh (lịch sử).
//   • Tạm ứng — ghi nhiều lần → duyệt → tự trừ.
//   • Cấu hình lương — 3 tab con: bậc lương & KPI · cơ chế theo bộ phận · phụ cấp & bảo hiểm.
//   • Phiếu lương của tôi — self-service.
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  Calculator,
  Receipt,
  HandCoins,
} from "lucide-react";
import {
  api,
  PIT_MODE_META,
  PIT_MODE_ORDER,
  type ComponentKind,
  type EmployeeDetail,
  type EmployeeInput,
  type EmployeeRow,
  type EmployeeSalary,
  type LineComponent,
  type PayrollComponent,
  type PayrollLine,
  type PayrollParams,
  type PayrollPeriod,
  type MyAdvances,
  type PitMode,
  type SalaryAdvance,
  type SalaryPreview,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { fmtDateTime } from "../utils/format";
import { printAdvanceRequest } from "../utils/printAdvanceRequest";
import { CauHinhLuongTab } from "./CauHinhLuongTab";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DiscardChangesDialog } from "../components/DiscardChangesDialog";
import { KhoanRatesEditor } from "../components/KhoanRatesEditor";
import "./nhan-su.css";
import "./luong.css";

type Tab =
  | "bang"
  | "nhanvien"
  | "khoan"
  | "tamung"
  | "cauhinh"
  | "phieu"
  | "tamung-me";

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

/** 6 cột thưởng NGỪNG GHI từ 28/07/2026 — giữ lại vì kỳ đã chốt vẫn có số. */
function legacyBonusRows(l: PayrollLine): [string, number][] {
  return (
    [
      ["Phép năm", l.phep_nam],
      ["Thưởng 5S", l.thuong_5s],
      ["Thưởng doanh số", l.thuong_doanh_so],
      ["Thưởng thành tích", l.thuong_thanh_tich],
      ["Trả đồng phục", l.tra_dong_phuc],
      ["Thưởng khác", l.other_bonus],
    ] as [string, number][]
  ).filter(([, v]) => (v ?? 0) !== 0);
}

/** Từng khoản THƯỞNG của kỳ này (cột "Thưởng" trên bảng + tooltip).
 *
 * ⚠️ CHỈ khoản `source='line'`. Khoản từ hồ sơ đã nằm trong `allowance` → hiện ở cột "Phụ cấp";
 * gộp cả hai vào đây là bảng đếm đôi tiền của cùng một khoản. */
function bonusRows(l: PayrollLine): [string, number][] {
  return [
    ...(l.components ?? [])
      .filter((c) => c.kind !== "tru" && c.source === "line")
      .map(
        (c) =>
          [c.note ? `${c.name} (${c.note})` : c.name, c.amount] as [
            string,
            number,
          ],
      ),
    ...legacyBonusRows(l),
  ];
}
function bonusTotal(l: PayrollLine): number {
  return bonusRows(l).reduce((s, [, v]) => s + v, 0);
}
function bonusTitle(l: PayrollLine): string {
  const rows = bonusRows(l);
  return rows.length
    ? rows.map(([k, v]) => `${k}: ${money(v)}`).join(" · ")
    : "";
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

      <nav className="ns-tabs cc-tabs lg-tabs" aria-label="Phân hệ Lương">
        <div className="lg-tabs__group">
          {canManage && (
            <button
              className={`lg-tab-btn ${tab === "bang" ? "is-active" : ""}`}
              onClick={() => go("bang")}
              title="Quản lý bảng lương tháng"
            >
              <Calendar className="lg-tab-btn__icon" />
              <span>Bảng lương tháng</span>
            </button>
          )}
          {canManage && (
            <button
              className={`lg-tab-btn ${tab === "nhanvien" ? "is-active" : ""}`}
              onClick={() => go("nhanvien")}
              title="Khai báo & điều chỉnh lương nhân viên"
            >
              <Users className="lg-tab-btn__icon" />
              <span>Lương nhân viên</span>
            </button>
          )}
          {canManage && (
            <button
              className={`lg-tab-btn ${tab === "khoan" ? "is-active" : ""}`}
              onClick={() => go("khoan")}
              title="Quản lý lương khoán"
            >
              <Calculator className="lg-tab-btn__icon" />
              <span>Lương khoán</span>
            </button>
          )}
          {canManage && (
            <button
              className={`lg-tab-btn ${tab === "tamung" ? "is-active" : ""}`}
              onClick={() => go("tamung")}
              title="Duyệt & quản lý tạm ứng"
            >
              <Wallet className="lg-tab-btn__icon" />
              <span>Tạm ứng</span>
            </button>
          )}
          {canReadConfig && (
            <button
              className={`lg-tab-btn ${tab === "cauhinh" ? "is-active" : ""}`}
              onClick={() => go("cauhinh")}
              title="Cấu hình thang bậc lương & cơ chế"
            >
              <Sliders className="lg-tab-btn__icon" />
              <span>Cấu hình lương</span>
              {cfgDirty && (
                <span className="lg-tab-badge lg-tab-badge--dirty" title="Có thay đổi chưa lưu">•</span>
              )}
            </button>
          )}
        </div>

        {canManage && <div className="lg-tabs__divider" aria-hidden="true" />}

        <div className="lg-tabs__group lg-tabs__group--personal">
          <button
            className={`lg-tab-btn ${tab === "phieu" ? "is-active" : ""}`}
            onClick={() => go("phieu")}
            title="Xem phiếu lương cá nhân"
          >
            <Receipt className="lg-tab-btn__icon" />
            <span>Phiếu lương của tôi</span>
          </button>
          <button
            className={`lg-tab-btn ${tab === "tamung-me" ? "is-active" : ""}`}
            onClick={() => go("tamung-me")}
            title="Đề nghị & theo dõi tạm ứng cá nhân"
          >
            <HandCoins className="lg-tab-btn__icon" />
            <span>Tạm ứng của tôi</span>
          </button>
        </div>
      </nav>

      {tab === "bang" && canManage && <BangLuongTab token={token!} />}
      {tab === "nhanvien" && canManage && (
        <NhanVienTab token={token!} focusEmployeeId={focusEmployeeId} />
      )}
      {tab === "khoan" && canManage && <KhoanTab token={token!} />}
      {tab === "tamung" && canManage && (
        <TamUngTab token={token!} eventTick={eventTick} />
      )}
      {tab === "cauhinh" && canReadConfig && (
        <CauHinhLuongTab
          token={token!}
          readOnly={!canManage}
          onDirtyChange={setCfgDirty}
        />
      )}
      {tab === "phieu" && <PhieuLuongTab token={token!} />}
      {tab === "tamung-me" && (
        <TamUngCuaToiTab token={token!} eventTick={eventTick} />
      )}

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
  const [q, setQ] = useState("");
  const [dept, setDept] = useState("all");
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

  // Danh sách Phòng/Tổ lấy từ CHÍNH các dòng lương đang có, không gọi thêm API: kỳ lương nào
  // cũng chỉ gồm người có mặt trong kỳ đó, nên đổ cả cây phòng ban ra là bày cả những tổ không
  // có ai để lọc.
  const dsPhong = useMemo(
    () =>
      Array.from(
        new Set(lines.map((l) => (l.department_name ?? "").trim()).filter(Boolean)),
      ).sort((a, b) => a.localeCompare(b, "vi")),
    [lines],
  );

  const kw = q.trim().toLowerCase();
  const shown = lines.filter((l) => {
    if (filter !== "all" && (filter === "tv") !== l.is_probation) return false;
    if (dept !== "all" && (l.department_name ?? "").trim() !== dept) return false;
    if (!kw) return true;
    // Tìm theo CẢ mã lẫn họ tên — người trả lương gõ mã, người soát gõ tên.
    return (
      (l.employee_name ?? "").toLowerCase().includes(kw) ||
      (l.employee_code ?? "").toLowerCase().includes(kw)
    );
  });
  const totalNet = shown.reduce((s, l) => s + l.net_pay, 0);
  const totalStaff = shown.length;
  const officialCount = shown.filter((l) => !l.is_probation).length;
  const probationCount = shown.filter((l) => l.is_probation).length;
  const totalWorkdays = shown.reduce((s, l) => s + (l.actual_cong ?? 0), 0);
  const totalDeductions = shown.reduce(
    (s, l) =>
      s +
      (l.vi_pham ?? 0) +
      (l.bhxh ?? 0) +
      (l.advance_total ?? 0) +
      (l.luong_dot_1_total ?? 0),
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
        {dsPhong.length > 1 && (
          <select
            className="lg-dept-filter"
            value={dept}
            onChange={(e) => setDept(e.target.value)}
            title="Lọc theo Phòng / Tổ"
          >
            <option value="all">Tất cả phòng / tổ</option>
            {dsPhong.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        )}
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
                    <span className="lg-source-name">
                      Thang bậc lương của tổ
                    </span>
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
                      l.night_pay
                        ? `phụ cấp ca (tay) ${money(l.night_pay)}`
                        : "",
                      l.night_premium_pay
                        ? `premium giờ×hệ số ${money(l.night_premium_pay)}`
                        : "",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  >
                    {l.night_pay || l.night_premium_pay
                      ? money((l.night_pay ?? 0) + (l.night_premium_pay ?? 0))
                      : "—"}
                  </td>
                  <td className={`lg-num ${l.vi_pham ? "lg-minus" : ""}`}>
                    {l.vi_pham ? "−" + money(l.vi_pham) : "—"}
                  </td>
                  {/* "Thưởng" = khoản PHÁT SINH kỳ này (`source='line'`) + 6 cột thưởng cũ đã
                      ngừng ghi. Khoản từ hồ sơ KHÔNG tính ở đây — nó nằm ở cột "Phụ cấp"
                      (`allowance`); cộng cả hai là đếm đôi trên bảng. */}
                  <td className="lg-num" title={bonusTitle(l)}>
                    {bonusTotal(l) ? money(bonusTotal(l)) : "—"}
                  </td>
                  <td className="lg-num lg-minus">
                    {l.bhxh ? "−" + money(l.bhxh) : "—"}
                  </td>
                  <td
                    className={`lg-num ${l.advance_total || l.luong_dot_1_total ? "lg-minus" : ""}`}
                  >
                    {l.luong_dot_1_total ? (
                      <div title="Thanh toán lương đợt 1">
                        −{money(l.luong_dot_1_total)}
                      </div>
                    ) : null}
                    {l.advance_total ? (
                      <div title="Tạm ứng đã nhận">
                        −{money(l.advance_total)}
                      </div>
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
                    <button
                      className="btn btn--ghost"
                      onClick={() => setPrinting(l)}
                    >
                      In
                    </button>
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
          readOnly={!isDraft}
          // Khối "Khoản phát sinh" lưu NGAY từng thao tác ⇒ đóng màn cũng phải tải lại bảng,
          // không thì cột phụ cấp / TNCN của dòng đó còn là số trước khi thêm khoản.
          onClose={() => {
            setEditing(null);
            load();
          }}
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
              <button className="ns-modal__x" onClick={() => setPrinting(null)}>
                ×
              </button>
            </header>
            <div className="ns-modal__body">
              <PayslipCard line={printing} period={period} />
            </div>
            <footer className="ns-modal__foot lg-payslip-noprint">
              <button
                className="btn btn--ghost"
                onClick={() => setPrinting(null)}
              >
                Đóng
              </button>
              <button
                className="btn btn--primary"
                onClick={() => window.print()}
              >
                🖨 In phiếu
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}

/** 2 khoản "mở" seed sẵn cho khoản lặt vặt (thưởng nóng) — đưa LÊN ĐẦU dropdown khoản phát
 *  sinh để không ai phải đẻ một danh mục mới dùng đúng một lần rồi bỏ. */
const OPEN_COMPONENT_CODES = ["thu_nhap_khac_ct", "thu_nhap_khac_mt"];

function LineEditModal({
  token,
  line,
  readOnly,
  onClose,
  onSaved,
}: {
  token: string;
  line: PayrollLine;
  /** Kỳ đã chốt / đã chi ⇒ khối "Khoản phát sinh" chỉ đọc (backend cũng chặn — 409). */
  readOnly: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [viPham, setViPham] = useState(line.vi_pham);
  const [note, setNote] = useState(line.note ?? "");
  // ⚠️ KHÔNG còn ô thưởng ở đây (chủ 28/07/2026: "khoản 5s hay thưởng gì thì cho nó select từ
  // quy tắc, để coi nó chịu thuế hay không"). 5 ô thưởng + "Thưởng khác" đã bị gỡ; thưởng khai ở
  // khối "Khoản phát sinh tháng này" bên dưới. Backend cũng đã bỏ chúng khỏi `LineUpdateIn`.
  const [detail, setDetail] = useState({
    di_tre: line.di_tre,
    dt_vuot_troi: line.dt_vuot_troi,
    phat_bien_ban: line.phat_bien_ban,
    phat_5s_dong_phuc: line.phat_5s_dong_phuc,
  });
  // Cột thưởng CŨ còn số (kỳ chốt trước 28/07/2026, hoặc dòng migration cố ý không đụng vì HCNS
  // đã tự thêm khoản trùng) → hiện CHỈ ĐỌC để tổng trên màn khớp phiếu, không cho sửa.
  const legacyBonus = legacyBonusRows(line);
  const setD = (k: keyof typeof detail, v: number) =>
    setDetail((d) => ({ ...d, [k]: v }));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Ô "Đi trễ": mặc định TỰ ĐỘNG từ chấm công. `di_tre_manual` = HCNS đã ghi đè tay.
  const [diTreManual, setDiTreManual] = useState(line.di_tre_manual);

  // --- TẦNG 3: khoản PHÁT SINH của riêng kỳ này (thưởng nóng) ---------------
  // Mỗi thao tác gọi API NGAY (backend tính lại dòng lương ngay lúc đó), KHÔNG gom vào nút
  // "Lưu" chung — gom lại thì số tổng trên màn và số thật trong DB lệch nhau giữa chừng.
  // null = ĐANG TẢI (khởi tạo [] sẽ báo "chưa có khoản nào" lúc còn fetch — sai).
  const [lcRows, setLcRows] = useState<LineComponent[] | null>(null);
  const [lcErr, setLcErr] = useState<string | null>(null);
  const [lcOk, setLcOk] = useState<string | null>(null);
  const [lcBusyId, setLcBusyId] = useState<number | null>(null);
  const [lcDraft, setLcDraft] = useState<
    Record<number, { amount: number; note: string }>
  >({});
  const [lcCatalog, setLcCatalog] = useState<PayrollComponent[] | null>(null);
  const [lcCatalogErr, setLcCatalogErr] = useState<string | null>(null);
  const [lcAdd, setLcAdd] = useState<{
    component_id: number;
    amount: number;
    note: string;
  } | null>(null);
  const [lcAddBusy, setLcAddBusy] = useState(false);
  // Sửa khoản ⇒ backend tính lại dòng ⇒ các số tổng ở đầu modal (`line`) thành CŨ. Nói ra chứ
  // đừng để người dùng đọc số cũ tưởng là số mới.
  const [lcTouched, setLcTouched] = useState(false);

  const loadLineComps = useCallback(async () => {
    try {
      const r = await api.luong.lineComponents(token, line.id);
      setLcRows(r.items);
      // GIỮ nháp của dòng còn tồn tại: tải lại sau khi xoá/sửa một dòng khác mà xoá trắng số
      // đang gõ dở ở dòng bên cạnh là mất công gõ lại (và dễ gõ nhầm số tiền lần hai).
      setLcDraft((prev) =>
        Object.fromEntries(
          r.items.map((x) => [
            x.id,
            prev[x.id] ?? { amount: x.amount, note: x.note ?? "" },
          ]),
        ),
      );
      setLcErr(null);
    } catch (e) {
      setLcErr(errText(e));
    }
  }, [token, line.id]);
  useEffect(() => {
    void loadLineComps();
  }, [loadLineComps]);
  useEffect(() => {
    if (readOnly) return; // chỉ đọc thì không cần danh mục để thêm
    let alive = true;
    api.luong.components
      .list(token)
      .then((r) => {
        if (!alive) return;
        setLcCatalog(r.items);
        setLcCatalogErr(null);
      })
      .catch((e) => {
        if (!alive) return;
        setLcCatalogErr(errText(e));
      });
    return () => {
      alive = false;
    };
  }, [token, readOnly]);

  /** Khoản chọn được khi thêm phát sinh: đang bật, 2 khoản "Thu nhập khác" lên đầu. KHÔNG lọc
   *  khoản đã có trên dòng — cùng một khoản có thể phát sinh 2 lần với 2 lý do khác nhau. */
  const lcAddable = (lcCatalog ?? [])
    .filter((c) => c.is_active)
    .slice()
    .sort((a, b) => {
      const ia = OPEN_COMPONENT_CODES.indexOf(a.code);
      const ib = OPEN_COMPONENT_CODES.indexOf(b.code);
      if (ia !== ib) return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
      return a.sort_order - b.sort_order;
    });

  async function lcRun(id: number, fn: () => Promise<unknown>, okMsg: string) {
    setLcBusyId(id);
    setLcErr(null);
    setLcOk(null);
    try {
      await fn();
      await loadLineComps();
      setLcTouched(true);
      setLcOk(okMsg);
    } catch (e) {
      setLcErr(errText(e));
    } finally {
      setLcBusyId(null);
    }
  }

  async function addLineComp() {
    if (!lcAdd) return;
    if (!lcAdd.component_id) {
      setLcErr("Chọn khoản trong danh mục trước.");
      return;
    }
    if (lcAdd.amount <= 0) {
      setLcErr("Nhập số tiền của khoản phát sinh.");
      return;
    }
    setLcAddBusy(true);
    setLcErr(null);
    setLcOk(null);
    try {
      await api.luong.addLineComponent(token, line.id, {
        component_id: lcAdd.component_id,
        amount: lcAdd.amount,
        note: lcAdd.note.trim() || null,
      });
      setLcAdd(null);
      await loadLineComps();
      setLcTouched(true);
      setLcOk("Đã thêm khoản phát sinh cho kỳ này.");
    } catch (e) {
      setLcErr(errText(e));
    } finally {
      setLcAddBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      // TNCN LUÔN tự tính theo Biểu thuế lũy tiến — KHÔNG gửi `pit`; ép `pit_manual:false`
      // để backend tính lại TNCN theo thu nhập chịu thuế mới (không cho sửa tay).
      const { di_tre, ...restDetail } = detail;
      const input = {
        vi_pham: viPham,
        pit_manual: false,
        note: note || null,
        ...restDetail,
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
          </div>
          {legacyBonus.length > 0 && (
            <>
              <h4 className="ns-section__title" style={{ marginTop: 14 }}>
                Khoản kỳ cũ{" "}
                <span className="ns-badge ns-badge--muted">chỉ đọc</span>
              </h4>
              <p className="cc-note">
                Các ô thưởng nhập tay đã ngừng dùng từ 28/07/2026 — nay khai ở{" "}
                <b>Khoản phát sinh tháng này</b> để chọn được chịu thuế hay miễn
                thuế. Số dưới đây là của kỳ cũ, <b>vẫn được trả</b> và giữ
                nguyên để phiếu lương đã ký không đổi.
              </p>
              <div className="lg-legacy">
                {legacyBonus.map(([lbl, v]) => (
                  <div className="lg-legacy__row" key={lbl}>
                    <span>{lbl}</span>
                    <b>{money(v)}đ</b>
                  </div>
                ))}
              </div>
            </>
          )}
          <h4 className="ns-section__title" style={{ marginTop: 12 }}>
            Các khoản giảm trừ (phạt)
          </h4>
          <div className="ns-grid">
            <label className="ns-field">
              <span className="ns-field__label">
                Đi trễ / nghỉ KP{" "}
                <span
                  className={`ns-badge ${diTreManual ? "ns-badge--muted" : "ns-badge--ok"}`}
                >
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
                    <button
                      type="button"
                      className="lg-linkbtn"
                      onClick={() => setDiTreManual(false)}
                    >
                      ↩ Về tự động từ chấm công
                    </button>
                  </>
                ) : (
                  <>
                    Tự tính từ chấm công (bảng phạt × số phút trễ/về sớm KHÔNG
                    phép mỗi ngày).{" "}
                    <button
                      type="button"
                      className="lg-linkbtn"
                      onClick={() => setDiTreManual(true)}
                    >
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
          {/* TẦNG 3 — khoản chỉ có ở KỲ NÀY. Khoản gán ở hồ sơ được trả LẶP LẠI mọi tháng
              (quên gỡ là trả mãi); khoản ở đây không lặp. Mỗi thao tác lưu NGAY. */}
          <h4 className="ns-section__title" style={{ marginTop: 14 }}>
            Khoản phát sinh tháng này
          </h4>
          <p className="cc-note">
            Khoản ở đây <b>chỉ có ở kỳ này, không lặp sang tháng sau</b> — đúng
            chỗ để khai thưởng nóng. Khoản trả đều hằng tháng thì gán ở{" "}
            <b>Lương → Lương nhân viên → Sửa lương</b>. Thao tác ở khối này{" "}
            <b>lưu ngay</b>, không chờ nút “Lưu” bên dưới.
          </p>
          {lcErr && <div className="banner banner--error">{lcErr}</div>}
          {lcOk && <div className="banner banner--success">{lcOk}</div>}
          <div className="lg-lc">
            <div className="lg-lc__head">
              <span>Khoản</span>
              <span>Thuế TNCN</span>
              <span>Số tiền</span>
              <span>Ghi chú</span>
              <span />
            </div>
            {lcRows === null ? (
              <div className="lg-lc__empty">
                {lcErr ? (
                  <button
                    type="button"
                    className="lg-linkbtn"
                    onClick={() => void loadLineComps()}
                  >
                    Thử tải lại
                  </button>
                ) : (
                  "Đang tải khoản của dòng lương…"
                )}
              </div>
            ) : lcRows.length === 0 ? (
              <div className="lg-lc__empty">
                Kỳ này chưa có khoản nào ngoài các ô lương ở trên.
              </div>
            ) : (
              lcRows.map((r) => {
                const fromEmp = r.source === "employee";
                const d = lcDraft[r.id] ?? {
                  amount: r.amount,
                  note: r.note ?? "",
                };
                const dirty =
                  d.amount !== r.amount || (d.note.trim() || null) !== r.note;
                const rowBusy = lcBusyId === r.id;
                return (
                  <div
                    key={r.id}
                    className={`lg-lc__row${fromEmp ? " lg-lc__row--emp" : ""}`}
                  >
                    <div className="lg-lc__name">
                      {r.name}
                      {fromEmp && (
                        <span
                          className="ns-badge ns-badge--muted"
                          style={{ marginLeft: 6 }}
                        >
                          Từ hồ sơ
                        </span>
                      )}
                      {fromEmp && (
                        <span className="lg-lc__src">
                          sửa ở Lương → Lương nhân viên
                        </span>
                      )}
                    </div>
                    <div>
                      <span
                        className={`ns-badge ${r.is_taxable ? "ns-badge--info" : "ns-badge--ok"}`}
                      >
                        {r.is_taxable ? "Chịu thuế" : "Miễn thuế"}
                      </span>
                    </div>
                    <div className="lg-lc__money">
                      {fromEmp || readOnly ? (
                        <span className="lg-lc__ro">{money(r.amount)}</span>
                      ) : (
                        <input
                          type="number"
                          min={0}
                          step={50000}
                          aria-label={`Số tiền khoản ${r.name}`}
                          value={d.amount}
                          disabled={rowBusy}
                          onChange={(e) =>
                            setLcDraft((s) => ({
                              ...s,
                              [r.id]: { ...d, amount: Number(e.target.value) },
                            }))
                          }
                        />
                      )}
                    </div>
                    <div className="lg-lc__note">
                      {fromEmp || readOnly ? (
                        <span className="lg-lc__ro">{r.note || "—"}</span>
                      ) : (
                        <input
                          type="text"
                          maxLength={255}
                          placeholder="vd: Thưởng nóng của Sếp"
                          aria-label={`Ghi chú khoản ${r.name}`}
                          value={d.note}
                          disabled={rowBusy}
                          onChange={(e) =>
                            setLcDraft((s) => ({
                              ...s,
                              [r.id]: { ...d, note: e.target.value },
                            }))
                          }
                        />
                      )}
                    </div>
                    <div className="lg-lc__act">
                      {!fromEmp && !readOnly && (
                        <>
                          {dirty && (
                            <button
                              type="button"
                              className="btn btn--ghost"
                              disabled={rowBusy}
                              onClick={() =>
                                void lcRun(
                                  r.id,
                                  () =>
                                    api.luong.updateLineComponent(token, r.id, {
                                      amount: d.amount,
                                      note: d.note.trim() || null,
                                    }),
                                  `Đã lưu khoản “${r.name}”.`,
                                )
                              }
                            >
                              Lưu
                            </button>
                          )}
                          <button
                            type="button"
                            className="btn btn--ghost"
                            disabled={rowBusy}
                            onClick={() =>
                              void lcRun(
                                r.id,
                                () =>
                                  api.luong.deleteLineComponent(token, r.id),
                                `Đã xoá khoản “${r.name}” khỏi kỳ này.`,
                              )
                            }
                          >
                            Xoá
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {readOnly ? (
            <p className="cc-card__hint">
              Kỳ lương đã chốt / đã chi — khối này chỉ để xem.
            </p>
          ) : lcAdd ? (
            <div className="lg-lc__add">
              <select
                className="lg-lc__pick"
                autoFocus
                aria-label="Chọn khoản phát sinh"
                value={lcAdd.component_id || ""}
                onChange={(e) =>
                  setLcAdd({ ...lcAdd, component_id: Number(e.target.value) })
                }
              >
                <option value="">— chọn khoản trong danh mục —</option>
                {lcAddable.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} · {c.is_taxable ? "chịu thuế" : "miễn thuế"}
                    {c.kind === "tru" ? " · khấu trừ" : ""}
                  </option>
                ))}
                <option value="" disabled>
                  Không thấy khoản cần dùng? Tạo ở Cấu hình lương → Danh mục
                  khoản thu nhập.
                </option>
              </select>
              <input
                type="number"
                min={0}
                step={50000}
                placeholder="Số tiền"
                aria-label="Số tiền khoản phát sinh"
                value={lcAdd.amount || ""}
                onChange={(e) =>
                  setLcAdd({ ...lcAdd, amount: Number(e.target.value) })
                }
              />
              <input
                type="text"
                maxLength={255}
                placeholder="vd: Thưởng nóng của Sếp"
                aria-label="Ghi chú khoản phát sinh"
                value={lcAdd.note}
                onChange={(e) => setLcAdd({ ...lcAdd, note: e.target.value })}
              />
              <button
                type="button"
                className="btn btn--primary"
                disabled={lcAddBusy}
                onClick={() => void addLineComp()}
              >
                {lcAddBusy ? "Đang thêm…" : "Thêm"}
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={lcAddBusy}
                onClick={() => setLcAdd(null)}
              >
                Hủy
              </button>
            </div>
          ) : (
            <div className="lg-lc__add">
              <button
                type="button"
                className="btn btn--ghost"
                disabled={lcCatalog === null}
                onClick={() => {
                  setLcErr(null);
                  setLcAdd({ component_id: 0, amount: 0, note: "" });
                }}
              >
                + Thêm khoản phát sinh
              </button>
              {lcCatalog === null && (
                <span className="cc-card__hint">
                  {lcCatalogErr
                    ? `Không đọc được danh mục khoản thu nhập (${lcCatalogErr}) — chưa thêm khoản phát sinh được.`
                    : "Đang tải danh mục khoản thu nhập…"}
                </span>
              )}
            </div>
          )}
          {lcTouched && (
            <p className="cc-card__hint">
              Đã tính lại dòng lương này. Các số tổng ở đầu màn (phụ cấp · thu
              nhập tính thuế · TNCN) cập nhật sau khi đóng màn.
            </p>
          )}

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

/** TẦNG 2 — một khoản ĐANG ĐƯỢC GÁN cho NV (`employee_salary_components`), hiện ở modal Sửa
 *  lương. Bảng này CHỈ chứa khoản đang gán, không đổ phẳng cả danh mục: muốn thêm thì bấm
 *  "+ Thêm khoản thu nhập" và CHỌN từ danh mục gốc (quy trình 2 bước — không gõ tên tự do).
 *
 *  `saved`/`savedNote` = số đang nằm trên server (`saved === null` ⇒ dòng vừa chọn, CHƯA lưu)
 *  ⇒ chỉ gửi dòng nào lệch. `is_taxable` chép từ danh mục gốc, CHỈ ĐỌC ở đây. */
type CompRow = {
  component_id: number;
  name: string;
  kind: ComponentKind;
  is_taxable: boolean;
  /** false = danh mục đã NGỪNG ÁP DỤNG mà người này còn giữ ⇒ cảnh báo đỏ, tiền VẪN trả. */
  is_active: boolean;
  saved: number | null;
  savedNote: string | null;
  draft: number;
  note: string;
};

/** Ô lương HỆ THỐNG — bảng RIÊNG, KHÔNG trộn với khoản danh mục (chốt chủ 27/07/2026): nguồn
 *  số là `employee_salaries` chứ không phải danh mục, nên sửa được SỐ TIỀN nhưng KHÔNG gỡ
 *  được, và cờ chịu thuế do ENGINE quyết (đọc `payroll_service._compute` / `_auto_pit`).
 *
 *  `taxable` phải khớp engine, không đoán:
 *   · lương cơ bản + trách nhiệm → `luong_cong` ⇒ CHỊU thuế
 *   · chuyên cần                → `chuyen_can` ⇒ CHỊU thuế
 *   · phụ cấp thâm niên         → ⊂ `allowance` ⇒ CHỊU thuế
 *   · phụ cấp ca                → đi qua `night_pay`, `_auto_pit` TRỪ khỏi thu nhập chịu thuế
 *                                 (miễn như tăng ca/ca đêm) ⇒ MIỄN thuế */
type SysRow = {
  key: string;
  name: string;
  note: string;
  taxable: boolean;
  value: number;
  set: (v: number) => void;
  /** Khoản đã NGƯNG: cho xem số cũ để tra lịch sử nhưng không cho sửa (sửa cũng không ra tiền). */
  readOnly?: boolean;
};

function SalaryModal({
  token,
  emp,
  onClose,
}: {
  token: string;
  emp: EmployeeRow;
  onClose: () => void;
}) {
  const can = useCan();
  // `pit_mode` là field lương/BHXH của HỒ SƠ nhân sự ⇒ backend đòi `nhan_su:update` +
  // `nhan_su:edit_salary`. Thiếu quyền thì hiện chỉ-đọc chứ đừng cho bấm rồi im lặng không ăn.
  const canEditPit = can("nhan_su", "update") && can("nhan_su", "edit_salary");
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
  // % hoa hồng NV kinh doanh — nhập theo PHẦN TRĂM ở UI, lưu xuống là PHÂN SỐ. Sửa ở ĐÂY chứ
  // không ở drawer nhân sự: mỗi lần POST là một mốc lương MỚI mang TOÀN BỘ các số, mà drawer
  // không giữ `luong_vi_tri`/phụ cấp ⇒ post từ đó là lương của người ta về 0.
  const [commissionPct, setCommissionPct] = useState(0);
  // Ô phụ cấp GỘP MỘT CỤC của dữ liệu cũ — chỉ đọc, giữ nguyên số để không mất tiền của NV;
  // khoản mới khai theo DANH MỤC ở `comps` bên dưới.
  const [allowance, setAllowance] = useState(0); // phụ cấp KHÁC (gộp — legacy)
  const [chuyenCan, setChuyenCan] = useState(0); // chuyên cần riêng NV
  // 2 phụ cấp khai tay còn lại. TRƯỚC ĐÂY modal không có 2 ô này nên mỗi lần bấm Lưu là chúng
  // bị ghi về 0 (mỗi lần lưu tạo MỘT mốc lương mới, field thiếu = mặc định 0) — mất tiền của NV.
  const [phuCapCa, setPhuCapCa] = useState(0);
  const [phuCapThamNien, setPhuCapThamNien] = useState(0);
  // TẦNG 2 — khoản ĐANG GÁN cho người này. null = ĐANG TẢI (khởi tạo [] sẽ báo "chưa gán khoản
  // nào" ngay lúc còn fetch — sai). `compBusy` khoá dòng đang gọi "Gỡ".
  const [comps, setComps] = useState<CompRow[] | null>(null);
  const [compBusy, setCompBusy] = useState<number | null>(null);
  const [compsErr, setCompsErr] = useState<string | null>(null);
  // Danh mục GỐC (Tầng 1) — chỉ để dựng dropdown "+ Thêm khoản". null = chưa đọc được (đang
  // tải hoặc thiếu quyền cấu hình) ⇒ khoá nút thêm chứ không chặn cả bảng.
  const [catalog, setCatalog] = useState<PayrollComponent[] | null>(null);
  const [catalogErr, setCatalogErr] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  // BH đóng ở nơi khác → công ty không trừ BHXH/BHYT/BHTN của NV, chỉ chịu TNLĐ-BNN.
  const [insuranceElsewhere, setInsuranceElsewhere] = useState(false);
  // Đoàn viên công đoàn → mới bị trừ đoàn phí công đoàn (mặc định không).
  const [unionMember, setUnionMember] = useState(false);
  // Giảm trừ bản thân — luật cho đăng ký ở ĐÚNG MỘT nơi làm việc. Mặc định BẬT (đại đa số chỉ
  // làm một nơi); tắt là ngoại lệ.
  const [applySelfDeduction, setApplySelfDeduction] = useState(true);
  const [params, setParams] = useState<PayrollParams | null>(null); // tỷ lệ BHXH/BHYT/BHTN + trần
  // Hồ sơ NV — chỉ để đọc `pit_mode` + `dependents_count` cho khối thuế. null = đang tải HOẶC
  // không đọc được (thiếu `nhan_su:read`): khối thuế lùi về chỉ-đọc chứ không chặn cả modal.
  const [detail, setDetail] = useState<EmployeeDetail | null>(null);
  const [detailErr, setDetailErr] = useState<string | null>(null);
  const [pitMode, setPitMode] = useState<PitMode | null>(null);
  const [pitConfirm, setPitConfirm] = useState(false);

  const reload = useCallback(async () => {
    const [prev, hist] = await Promise.all([
      api.luong.salaryPreview(token, emp.id).catch(() => null),
      api.luong.salaries(token, emp.id).catch(() => ({
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
      setPhuCapCa(latest.phu_cap_ca ?? 0);
      setPhuCapThamNien(latest.phu_cap_tham_nien ?? 0);
      setLuongDot1(latest.luong_dot_1 ?? 0);
      setCommissionPct((latest.commission_pct ?? 0) * 100);
      setInsuranceElsewhere(!!latest.insurance_elsewhere);
      setUnionMember(!!latest.union_member);
      setApplySelfDeduction(latest.apply_self_deduction ?? true);
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
  // Hồ sơ NV cho khối thuế TNCN. `pit_mode` về null = backend CHE (thiếu `nhan_su:view_salary`)
  // chứ không phải chưa khai ⇒ khoá sửa, và tuyệt đối không gửi lại null (schema có pattern ⇒ 422).
  useEffect(() => {
    let alive = true;
    api.employees
      .get(token, emp.id)
      .then((d) => {
        if (!alive) return;
        setDetail(d);
        setPitMode(d.pit_mode);
        setDetailErr(null);
      })
      .catch((e) => {
        if (!alive) return;
        setDetail(null);
        setPitMode(null);
        setDetailErr(errText(e));
      });
    return () => {
      alive = false;
    };
  }, [token, emp.id]);

  // Bảng khoản = đúng những khoản NGƯỜI NÀY đang được gán (`/components/employee/{id}` chỉ trả
  // khoản có tiền). KHÔNG đổ phẳng cả danh mục ra thành ô tiền — màn dài ngoằng và không ai
  // biết khoản nào đang thật sự áp dụng.
  const loadComps = useCallback(async () => {
    try {
      const r = await api.luong.components.employeeValues(token, emp.id);
      setComps(
        r.items.map((v) => ({
          component_id: v.component_id,
          name: v.name,
          kind: v.kind,
          is_taxable: v.is_taxable,
          is_active: v.is_active,
          saved: v.amount,
          savedNote: v.note,
          draft: v.amount,
          note: v.note ?? "",
        })),
      );
      setCompsErr(null);
    } catch (e) {
      // GIỮ NGUYÊN `comps`: gán [] khi lỗi sẽ báo "chưa gán khoản nào" — sai, và người dùng
      // sẽ gán lại từ đầu thành gán trùng.
      setCompsErr(errText(e));
    }
  }, [token, emp.id]);
  useEffect(() => {
    loadComps();
  }, [loadComps]);
  // Danh mục gốc chỉ để dựng dropdown "+ Thêm khoản" — đọc hỏng thì khoá nút thêm, bảng khoản
  // đang gán vẫn dùng bình thường.
  useEffect(() => {
    let alive = true;
    api.luong.components
      .list(token)
      .then((r) => {
        if (!alive) return;
        setCatalog(r.items);
        setCatalogErr(null);
      })
      .catch((e) => {
        if (!alive) return;
        setCatalogErr(errText(e));
      });
    return () => {
      alive = false;
    };
  }, [token]);

  function setRow(id: number, patch: Partial<CompRow>) {
    setComps((list) =>
      (list ?? []).map((r) => (r.component_id === id ? { ...r, ...patch } : r)),
    );
  }

  /** Khoản CHƯA gán cho người này + đang bật — đúng tập được phép chọn. Khoản đã gán ẩn khỏi
   *  danh sách (chống gán trùng, đúng ràng buộc UNIQUE ở DB); khoản đã ngừng áp dụng cũng ẩn
   *  (backend chặn gán mới). */
  const assigned = new Set((comps ?? []).map((r) => r.component_id));
  const addable = (catalog ?? []).filter(
    (c) => c.is_active && !assigned.has(c.id),
  );

  /** Chọn khoản từ danh mục ⇒ thêm MỘT dòng nháp (chưa gọi API). Số tiền + ghi chú gõ xong
   *  mới bấm "Lưu điều chỉnh" — cùng một nhịp lưu với các ô lương, không lưu lắt nhắt. */
  function addComp(componentId: number) {
    const c = (catalog ?? []).find((x) => x.id === componentId);
    if (!c) return;
    setComps((list) => [
      ...(list ?? []),
      {
        component_id: c.id,
        name: c.name,
        kind: c.kind,
        is_taxable: c.is_taxable,
        is_active: c.is_active,
        saved: null,
        savedNote: null,
        draft: 0,
        note: "",
      },
    ]);
    setPicking(false);
  }

  /** "Gỡ" = thôi trả khoản này cho người đó từ kỳ sau (`amount: null`). Dòng chưa lưu thì chỉ
   *  bỏ khỏi màn. Dòng đã lưu gọi API NGAY — đây là lệnh dứt điểm, gom vào nút Lưu chung sẽ
   *  làm người dùng tưởng đã gỡ trong khi tiền vẫn đang chạy. */
  async function removeComp(row: CompRow) {
    if (row.saved === null) {
      setComps((list) =>
        (list ?? []).filter((r) => r.component_id !== row.component_id),
      );
      return;
    }
    setCompBusy(row.component_id);
    setErr(null);
    try {
      await api.luong.components.setEmployeeValues(token, emp.id, [
        { component_id: row.component_id, amount: null },
      ]);
      setComps((list) =>
        (list ?? []).filter((r) => r.component_id !== row.component_id),
      );
      setOk(
        `Đã gỡ khoản “${row.name}” khỏi ${emp.full_name}. Kỳ lương đã chốt giữ nguyên số cũ.`,
      );
    } catch (e) {
      setErr(errText(e));
    } finally {
      setCompBusy(null);
    }
  }

  /** Đổi cách tính thuế = đổi TIỀN THUẾ của người đó (bỏ/lấy lại giảm trừ gia cảnh) ⇒ hỏi lại
   *  trước khi lưu, không để bấm nhầm. Không đổi nhánh thì lưu thẳng. */
  const pitChanged =
    canEditPit &&
    pitMode != null &&
    detail != null &&
    pitMode !== detail.pit_mode;
  function saveSalary() {
    if (pitChanged) {
      setPitConfirm(true);
      return;
    }
    void doSave();
  }

  /** Dòng khoản có gì để gửi: đổi số, đổi ghi chú, hoặc là dòng mới chọn (`saved === null`). */
  const compChanged = (comps ?? []).filter(
    (r) =>
      r.saved === null ||
      r.draft !== r.saved ||
      (r.note.trim() || null) !== r.savedNote,
  );

  async function doSave() {
    setPitConfirm(false);
    // Khoản vừa chọn mà để 0 thì backend lưu 0 rồi lọc mất khi đọc lại — người dùng thấy khoản
    // "biến mất" và tưởng hệ thống nuốt. Chặn ngay ở đây, nói rõ phải làm gì.
    const emptyNew = compChanged.find((r) => r.saved === null && r.draft <= 0);
    if (emptyNew) {
      setErr(
        `Nhập số tiền cho khoản “${emptyNew.name}” (hoặc bấm Gỡ để bỏ dòng đó) rồi lưu lại.`,
      );
      return;
    }
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
        phu_cap_ca: phuCapCa,
        phu_cap_tham_nien: phuCapThamNien,
        insurance_elsewhere: insuranceElsewhere,
        union_member: unionMember,
        apply_self_deduction: applySelfDeduction,
        // Backend nhận PHÂN SỐ và chặn `le=1` ⇒ kẹp trần 100% ở đây, đừng để gõ nhầm "150"
        // ăn nguyên cục 422 mà không hiểu vì sao.
        commission_pct: Math.min(commissionPct, 100) / 100,
      });
      // Khoản danh mục: chỉ gửi dòng ĐỔI (số hoặc ghi chú) — gửi cả bảng là ghi lại hàng loạt
      // bản ghi không đổi, làm bẩn nhật ký và dễ ghi đè số người khác vừa sửa.
      if (compChanged.length) {
        await api.luong.components.setEmployeeValues(
          token,
          emp.id,
          compChanged.map((r) => ({
            component_id: r.component_id,
            amount: r.draft,
            note: r.note.trim() || null,
          })),
        );
        // Đọc LẠI từ server thay vì suy từ nháp: khoản để 0 bị backend lọc khỏi danh sách,
        // đoán bừa là màn hiện một dòng không còn tồn tại.
        await loadComps();
      }
      // Cách tính thuế nằm ở HỒ SƠ (`employees.pit_mode`) nên phải PUT hồ sơ. Endpoint này ghi
      // ĐÈ mọi field sửa được ⇒ gửi NGUYÊN bản hồ sơ vừa đọc, chỉ đổi đúng `pit_mode`; gửi
      // body rút gọn sẽ XOÁ TRẮNG số điện thoại / địa chỉ / STK của người ta.
      let pitNote = "";
      if (pitChanged && detail && pitMode) {
        // try RIÊNG: lương ĐÃ lưu xong ở trên rồi. Ném lỗi ra ngoài sẽ hiện mỗi câu đỏ và
        // người dùng tưởng KHÔNG có gì được lưu → gõ lại lần nữa, sinh thêm một mốc lương.
        try {
          const res = await api.employees.update(token, emp.id, {
            ...(detail as unknown as EmployeeInput),
            pit_mode: pitMode,
          });
          setDetail(res.employee);
          setPitMode(res.employee.pit_mode);
          // Thiếu `nhan_su:edit_salary` thì backend BỎ QUA field này mà KHÔNG báo lỗi — đọc lại
          // kết quả rồi mới nói, đừng báo "đã đổi" cho một việc chưa xảy ra.
          pitNote =
            res.employee.pit_mode === pitMode
              ? ` Cách tính thuế TNCN: ${PIT_MODE_META[pitMode].label}.`
              : " ⚠ Cách tính thuế TNCN CHƯA đổi được — tài khoản của bạn không có quyền sửa" +
                " dữ liệu lương/BHXH của hồ sơ nhân sự.";
        } catch (e) {
          setPitMode(detail.pit_mode); // trả ô về đúng số đang nằm trên server
          setErr(
            `Lương đã lưu, nhưng KHÔNG đổi được cách tính thuế TNCN: ${errText(e)}`,
          );
        }
      }
      setOk(
        "Đã lưu lương (hiệu lực từ hôm nay " + fmtYmd(eff) + ")." + pitNote,
      );
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
  const bhBase = luongViTri; // đóng BH trên lương cơ bản (vị trí)

  // Tổng khoản THU của danh mục (khoản `tru` là khấu trừ, không cộng vào đây) + số cũ gộp cục.
  const compThu = (comps ?? []).reduce(
    (s, r) => (r.kind === "thu" ? s + r.draft : s),
    0,
  );
  const compTru = (comps ?? []).reduce(
    (s, r) => (r.kind === "tru" ? s + r.draft : s),
    0,
  );
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

  // 5 ô lương HỆ THỐNG, đứng chung bảng với khoản danh mục (chốt chủ 27/07/2026). Cờ chịu thuế
  // bám ĐÚNG engine (xem chú thích type SysRow) — đây là nơi dễ "dạy sai" nhất của màn này.
  const sysRows: SysRow[] = [
    {
      key: "luong_vi_tri",
      name: "Lương cơ bản (đóng BH)",
      note: "BHXH/BHYT/BHTN đóng trên số này",
      taxable: true,
      value: luongViTri,
      set: setLuongViTri,
    },
    {
      key: "luong_trach_nhiem",
      name: "Lương trách nhiệm",
      note: `Mức nền = cơ bản + trách nhiệm: ${money(salaryBase)}đ — tăng ca tính trên số này`,
      taxable: true,
      value: luongTrachNhiem,
      set: setLuongTrachNhiem,
    },
    {
      key: "chuyen_can",
      name: "Thưởng chuyên cần",
      note: "Để 0 = dùng mức của tổ. Trừ dần theo ngày nghỉ",
      taxable: true,
      value: chuyenCan,
      set: setChuyenCan,
    },
    {
      key: "phu_cap_ca",
      name: "Phụ cấp ca (đã ngưng)",
      // Chú thích cũ ghi "engine miễn TNCN như tiền tăng ca / ca đêm" — câu đó KHẲNG ĐỊNH SAI:
      // phần miễn thuế là di sản từ hồi ô này là tiền ca đêm ĐƯỢC TÍNH, còn TT 111/2013 Đ3.1.i
      // chỉ miễn phần trả CAO HƠN gắn với giờ đêm/tăng ca THỰC TẾ.
      note: "KHÔNG còn ra tiền từ 03/08/2026 — cơm & phụ cấp ca nay tính theo CA THỰC LÀM (khai ở từng ca, màn Chấm công). Số cũ giữ lại để tra lịch sử.",
      taxable: true,
      value: phuCapCa,
      set: setPhuCapCa,
      readOnly: true,
    },
    {
      key: "phu_cap_tham_nien",
      name: "Phụ cấp thâm niên",
      note: "Số cố định khai tay, không tự tính theo năm công tác",
      taxable: true,
      value: phuCapThamNien,
      set: setPhuCapThamNien,
    },
  ];
  const sysThu = sysRows.reduce((s, r) => s + r.value, 0);

  // --- Khối thuế TNCN --------------------------------------------------------
  // Người phụ thuộc lấy từ HỒ SƠ (ô `dependents_count` đã có sẵn ở đó) — ở đây chỉ nhẩm hộ.
  const dependents = detail?.dependents_count ?? 0;
  // `pitKnown` = đã ĐỌC ĐƯỢC cách tính thuế thật của người này. Chưa đọc được (đang tải, thiếu
  // quyền, hoặc backend che) ⇒ không được đoán, và tuyệt đối không PUT đè.
  const pitKnown = detail != null && detail.pit_mode != null;
  const pitEff = pitMode ?? "luy_tien";
  const hasDeduction = pitEff === "luy_tien"; // 2 nhánh còn lại KHÔNG có giảm trừ gia cảnh

  // Khối "Cấu hình tính thuế TNCN" trong modal này ĐANG TẮT (JSX bị comment ở ~2494–2616). Giữ
  // nguyên phần tính ở trên để bật lại chỉ cần bỏ comment khối JSX. Mấy dòng `void` dưới đây chỉ
  // để TypeScript thôi báo "khai mà không dùng" — không chạy gì, không đổi hành vi.
  void PIT_MODE_ORDER;
  void detailErr;
  void pitKnown;
  void hasDeduction;
  const deductionSelf = params ? params.deduction_self : null;
  const deductionDependent = params ? params.deduction_dependent : null;
  const deductionTotal =
    deductionSelf == null || deductionDependent == null
      ? null
      : (applySelfDeduction ? deductionSelf : 0) +
        deductionDependent * dependents;

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
          {/* `banner--ok` KHÔNG có trong global.css ⇒ trước đây câu báo thành công hiện trần
              như chữ thường. Class đúng là `banner--success`. */}
          {ok && <div className="banner banner--success">{ok}</div>}

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

          {/* Ô lương HỆ THỐNG (`employee_salaries`) — GIỮ RIÊNG, không trộn với bảng khoản
              danh mục bên dưới: 5 ô này không gỡ được, trộn chung làm người dùng tưởng gỡ
              được. Cờ chịu thuế do ENGINE quyết (xem type SysRow) nên chỉ đọc. */}
          <h4 className="ns-section__title">Lương &amp; phụ cấp cố định</h4>
          <p className="cc-note">
            5 ô cố định của phần mềm: sửa được <b>số tiền</b>, không gỡ được.
            Khi lưu, mức mới <b>áp dụng từ hôm nay</b> và mốc cũ được giữ trong
            Lịch sử điều chỉnh.
          </p>
          <div className="lg-comp lg-comp--sys">
            <div className="lg-comp__head">
              <span>Khoản</span>
              <span>Thuế TNCN</span>
              <span>Số tiền / tháng</span>
            </div>
            {sysRows.map((r) => (
              <div key={r.key} className="lg-comp__row lg-comp__row--sys">
                <div className="lg-comp__name">
                  {r.name}
                  <span className="lg-comp__src">{r.note}</span>
                </div>
                <div>
                  <span
                    className={`ns-badge ${r.taxable ? "ns-badge--info" : "ns-badge--ok"}`}
                  >
                    {r.taxable ? "Chịu thuế" : "Miễn thuế"}
                  </span>
                </div>
                <div className="lg-comp__money">
                  <input
                    type="number"
                    min={0}
                    step={100000}
                    aria-label={`Số tiền ${r.name}`}
                    value={r.value}
                    // Ô đã ngưng: cho XEM số cũ nhưng KHÔNG cho sửa. Ẩn hẳn thì người ta không
                    // tra được lịch sử; để sửa được thì lại hứa suông vì số đó không ra tiền nữa.
                    readOnly={r.readOnly}
                    disabled={r.readOnly}
                    onChange={(e) => r.set(Number(e.target.value))}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* TẦNG 2 — khoản thu nhập theo DANH MỤC, gán cho riêng người này. Chỉ hiện khoản
              ĐANG GÁN; muốn thêm thì CHỌN từ danh mục gốc (bước 2 của quy trình 2 bước). */}
          <h4 className="ns-section__title" style={{ marginTop: 16 }}>
            Khoản thu nhập theo danh mục
          </h4>
          <p className="cc-note">
            Khoản gán ở đây được trả <b>lặp lại mọi tháng</b> cho tới khi bạn
            gỡ. Chip <b>Chịu thuế / Miễn thuế</b> kế thừa từ danh mục gốc —{" "}
            <b>không sửa ở đây</b>. Thưởng nóng chỉ có một tháng thì đừng gán
            vào đây: khai ở{" "}
            <b>Bảng lương → Sửa dòng → Khoản phát sinh tháng này</b>.
          </p>
          <div className="lg-comp lg-comp--cat">
            <div className="lg-comp__head">
              <span>Khoản</span>
              <span>Thuế TNCN</span>
              <span>Số tiền / tháng</span>
              <span>Ghi chú</span>
              <span />
            </div>
            {comps === null ? (
              <div className="lg-comp__empty">
                {compsErr ? (
                  <>
                    Không đọc được khoản của người này ({compsErr}).{" "}
                    <button
                      type="button"
                      className="lg-linkbtn"
                      onClick={() => void loadComps()}
                    >
                      Thử lại
                    </button>
                  </>
                ) : (
                  "Đang tải các khoản đang gán…"
                )}
              </div>
            ) : comps.length === 0 ? (
              <div className="lg-comp__empty">
                Người này chưa được gán khoản thu nhập nào. Bấm{" "}
                <b>“+ Thêm khoản thu nhập”</b> để chọn từ danh mục.
              </div>
            ) : (
              comps.map((r) => (
                <div
                  key={r.component_id}
                  className={`lg-comp__row${r.is_active ? "" : " lg-comp__row--off"}`}
                >
                  <div className="lg-comp__name">
                    {r.name}
                    {r.kind === "tru" && (
                      <span
                        className="ns-badge ns-badge--danger"
                        style={{ marginLeft: 6 }}
                      >
                        Trừ
                      </span>
                    )}
                    {r.saved === null && (
                      <span
                        className="ns-badge ns-badge--muted"
                        style={{ marginLeft: 6 }}
                      >
                        chưa lưu
                      </span>
                    )}
                    {/* Khoản đã ngừng áp dụng: CẢNH BÁO thôi, vẫn hiện số tiền bình thường —
                        lương đang trả khoản này, gạch ngang / ẩn đi là nói dối. */}
                    {!r.is_active && (
                      <span className="lg-comp__warn">
                        Khoản này đã ngừng áp dụng. Gỡ bỏ hoặc để 0.
                      </span>
                    )}
                  </div>
                  <div>
                    <span
                      className={`ns-badge ${r.is_taxable ? "ns-badge--info" : "ns-badge--ok"}`}
                    >
                      {r.is_taxable ? "Chịu thuế" : "Miễn thuế"}
                    </span>
                  </div>
                  <div className="lg-comp__money">
                    <input
                      type="number"
                      min={0}
                      step={50000}
                      aria-label={`Số tiền khoản ${r.name}`}
                      value={r.draft}
                      disabled={compBusy === r.component_id}
                      onChange={(e) =>
                        setRow(r.component_id, {
                          draft: Number(e.target.value),
                        })
                      }
                    />
                  </div>
                  <div className="lg-comp__note">
                    <input
                      type="text"
                      maxLength={255}
                      placeholder="vd: theo dự án X"
                      aria-label={`Ghi chú khoản ${r.name}`}
                      value={r.note}
                      disabled={compBusy === r.component_id}
                      onChange={(e) =>
                        setRow(r.component_id, { note: e.target.value })
                      }
                    />
                  </div>
                  <div className="lg-comp__act">
                    <button
                      type="button"
                      className="btn btn--ghost"
                      title="Thôi trả khoản này cho người đó (kỳ đã chốt giữ nguyên số cũ)"
                      disabled={compBusy === r.component_id}
                      onClick={() => void removeComp(r)}
                    >
                      Gỡ
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Thêm khoản = CHỌN từ danh mục gốc. KHÔNG có ô gõ tên tự do — muốn khoản mới thì
              phải tạo ở Cấu hình lương trước (quy trình 2 bước, chốt của chủ). */}
          <div className="lg-comp__add">
            {picking ? (
              <>
                <select
                  className="lg-comp__pick"
                  autoFocus
                  aria-label="Chọn khoản thu nhập từ danh mục"
                  value=""
                  onChange={(e) => {
                    if (e.target.value) addComp(Number(e.target.value));
                  }}
                >
                  <option value="">— chọn khoản trong danh mục —</option>
                  {addable.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} · {c.is_taxable ? "chịu thuế" : "miễn thuế"}
                      {c.kind === "tru" ? " · khấu trừ" : ""}
                    </option>
                  ))}
                  <option value="" disabled>
                    Không thấy khoản cần dùng? Tạo ở Cấu hình lương → Danh mục
                    khoản thu nhập.
                  </option>
                </select>
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => setPicking(false)}
                >
                  Hủy
                </button>
              </>
            ) : (
              <button
                type="button"
                className="btn btn--ghost"
                disabled={catalog === null || addable.length === 0}
                onClick={() => setPicking(true)}
              >
                + Thêm khoản thu nhập
              </button>
            )}
            {catalogErr && (
              <span className="cc-card__hint">
                Không đọc được danh mục khoản thu nhập ({catalogErr}) — chưa
                chọn thêm khoản được.
              </span>
            )}
            {catalog !== null && addable.length === 0 && !picking && (
              <span className="cc-card__hint">
                Đã gán hết khoản đang bật trong danh mục. Cần khoản mới thì tạo
                ở <b>Cấu hình lương → Danh mục khoản thu nhập</b>.
              </span>
            )}
          </div>

          <p className="cc-card__hint">
            Tổng cộng mỗi tháng: <b>{money(sysThu + compThu)}đ</b> (ô cố định{" "}
            {money(sysThu)}đ · khoản danh mục {money(compThu)}đ)
            {compTru > 0 && (
              <>
                {" · "}khấu trừ: <b>{money(compTru)}đ</b>
              </>
            )}
            . Để <b>0</b> = thôi trả khoản đó (lưu xong dòng sẽ rời khỏi bảng).
          </p>

          {/* "Lương trả 1 lần" KHÔNG phải khoản thu nhập hằng tháng (không cộng vào lương) nên
              để ngoài bảng — nó chỉ là số điền sẵn cho phiếu tạm ứng đợt 1. */}
          <div className="ns-grid" style={{ marginTop: 12 }}>
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
                Mức trả trong MỘT lần, KHÔNG cộng vào lương tháng. Đây chỉ là số
                điền sẵn — muốn trả đợt 1 thì sang tab <b>Tạm ứng</b> bấm{" "}
                <b>“+ Phiếu lương đợt 1”</b>, duyệt xong mới trừ vào lương.
              </span>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">
                % hoa hồng (NV kinh doanh)
              </span>
              <input
                type="number"
                min={0}
                max={100}
                step={0.5}
                placeholder="0"
                value={commissionPct || ""}
                onChange={(e) =>
                  setCommissionPct(
                    e.target.value === "" ? 0 : Number(e.target.value),
                  )
                }
              />
              <span className="cc-card__hint">
                Bỏ trống / 0 nếu không phải nhân viên kinh doanh.
                {/* Ô này <b>chỉ để KHAI</b> — hệ
                thống <b>CHƯA tự cộng hoa hồng vào lương</b>. Muốn trả thì vẫn phải thêm bằng tay
                ở <b>khoản thu nhập</b> của nhân viên hoặc ngay trên phiếu lương. */}
              </span>
            </label>
          </div>

          {/* Số phụ cấp GỘP MỘT CỤC của dữ liệu cũ — CHỈ ĐỌC, không xoá dữ liệu cũ. */}
          {allowance > 0 && (
            <div className="ns-field lg-legacy" style={{ marginTop: 12 }}>
              <span className="ns-field__label">
                Các khoản phụ cấp (số cũ, gộp một cục)
              </span>
              <input
                type="number"
                value={allowance}
                readOnly
                tabIndex={-1}
                aria-label="Các khoản phụ cấp gộp một cục (số cũ, chỉ đọc)"
              />
              <span className="cc-card__hint">
                Số cũ gộp một cục — nên tách ra từng khoản bên trên. Hệ thống
                vẫn cộng đủ số này như trước nên tách xong mà chưa bỏ số cũ là{" "}
                <b>cộng hai lần</b>.{" "}
                <button
                  type="button"
                  className="lg-linkbtn"
                  onClick={() => setAllowance(0)}
                >
                  Đưa về 0 sau khi đã tách
                </button>{" "}
                (các mốc lương cũ trong Lịch sử điều chỉnh vẫn giữ nguyên số).
              </span>
            </div>
          )}

          <label className="ns-check" style={{ marginTop: 6 }}>
            <input
              type="checkbox"
              checked={insuranceElsewhere}
              onChange={(e) => setInsuranceElsewhere(e.target.checked)}
            />
            Bảo hiểm đóng ở nơi khác — công ty chỉ đóng TNLĐ-BNN
          </label>
          <p className="cc-card__hint">
            Tích khi NV đã được nơi khác đóng BHXH/BHYT/BHTN. Công ty không trừ
            3 khoản này của họ.
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
            Chỉ đoàn viên mới bị trừ đoàn phí công đoàn (theo tỷ lệ ở Cấu hình
            lương). Không tích = không trừ.
          </p>

          {/* Cấu hình tính thuế TNCN theo TỪNG NGƯỜI. Mọi con số (giảm trừ, tỷ lệ khấu trừ,
              ngưỡng) LẤY TỪ `GET /api/luong/params` — viết cứng vào chuỗi là màn hình nói dối
              ngay lần luật đổi mức. */}
          {/* <h4 className="ns-section__title" style={{ marginTop: 16 }}>
            Cấu hình tính thuế TNCN
          </h4>
          {detailErr && (
            <p className="cc-card__hint">
              ⚠ Không đọc được hồ sơ nhân sự của người này ({detailErr}) — phần
              cách tính thuế và người phụ thuộc chỉ hiện được khi đọc được hồ
              sơ.
            </p>
          )}
          <div className="lg-pit">
            <label className="ns-field lg-pit__mode">
              <span className="ns-field__label">Cách tính thuế TNCN</span>
              <select
                value={pitKnown ? pitEff : ""}
                disabled={!canEditPit || !pitKnown}
                onChange={(e) => setPitMode(e.target.value as PitMode)}
              >
                {!pitKnown && (
                  <option value="">
                    {detail == null
                      ? "— đang đọc hồ sơ —"
                      : "— không xem được —"}
                  </option>
                )}
                {PIT_MODE_ORDER.map((m) => (
                  <option key={m} value={m}>
                    {PIT_MODE_META[m].label}
                  </option>
                ))}
              </select>
              {pitKnown && (
                <span className="cc-card__hint">
                  {PIT_MODE_META[pitEff].hint}
                  {pitEff === "khau_tru_10" && params && (
                    <>
                      {" "}
                      Thuế = <b>{pctOf(params.pit_flat_rate)}%</b> × thu nhập
                      chịu thuế, chỉ khấu trừ khi thu nhập chịu thuế đạt{" "}
                      <b>{money(params.pit_flat_threshold)}đ</b> trở lên.
                    </>
                  )}
                  {pitEff === "cam_ket_08" && (
                    <>
                      {" "}
                      Chỉ chọn khi đã nhận đủ bản cam kết và người này có mã số
                      thuế cá nhân.
                    </>
                  )}
                </span>
              )}
              {!canEditPit && (
                <span className="cc-card__hint">
                  Tài khoản của bạn không có quyền sửa nhóm dữ liệu lương/BHXH
                  của hồ sơ nhân sự nên ô này chỉ để xem.
                </span>
              )}
              {canEditPit && detail != null && detail.pit_mode == null && (
                <span className="cc-card__hint">
                  Không xem được cách tính thuế hiện tại của người này (thiếu
                  quyền xem dữ liệu lương của hồ sơ) — khoá sửa để không ghi đè
                  nhầm.
                </span>
              )}
            </label>

            <div
              className={`lg-pit__ded${hasDeduction ? "" : " lg-pit__ded--off"}`}
            >
              {!hasDeduction && (
                <p className="lg-pit__note">
                  Cách tính này <b>không áp dụng giảm trừ gia cảnh</b>.
                </p>
              )}
              <label className="ns-check">
                <input
                  type="checkbox"
                  checked={applySelfDeduction}
                  disabled={!hasDeduction}
                  onChange={(e) => setApplySelfDeduction(e.target.checked)}
                />
                Áp dụng giảm trừ bản thân
              </label>
              <p className="cc-card__hint">
                {deductionSelf == null ? (
                  "Đang đọc mức giảm trừ từ Cấu hình lương…"
                ) : (
                  <>
                    Giảm trừ <b>{money(deductionSelf)}đ</b>/tháng. Bỏ tích nếu
                    người này đã đăng ký giảm trừ ở nơi làm việc khác (chỉ được
                    đăng ký ở <b>MỘT</b> nơi).
                  </>
                )}
              </p>
              <div className="lg-pit__dep">
                <span className="lg-pit__dep-label">Người phụ thuộc</span>
                {detail == null ? (
                  <span className="lg-pit__dep-val">—</span>
                ) : (
                  <span className="lg-pit__dep-val">
                    <b>{dependents} người</b>
                    {deductionDependent != null && (
                      <>
                        {" → giảm trừ "}
                        <b>{money(deductionDependent * dependents)}đ</b>
                      </>
                    )}
                  </span>
                )}
              </div>
              <p className="cc-card__hint">
                Số người phụ thuộc khai ở{" "}
                <b>Nhân sự → hồ sơ → tab Lương &amp; BHXH</b>; ở đây chỉ nhẩm hộ
                ra tiền.
                {hasDeduction && deductionTotal != null && detail != null && (
                  <>
                    {" "}
                    Tổng giảm trừ mỗi tháng: <b>{money(deductionTotal)}đ</b>.
                  </>
                )}
              </p>
            </div>
          </div> */}

          <div className="ns-grid" style={{ marginTop: 12 }}>
            <div
              className="ns-field"
              style={{ alignItems: "flex-end", gap: 6 }}
            >
              {ok && (
                <span
                  style={{ color: "#2e7d32", fontSize: 13, fontWeight: 600 }}
                >
                  ✓ {ok}
                </span>
              )}
              {err && (
                <span
                  style={{ color: "#c62828", fontSize: 13, fontWeight: 600 }}
                >
                  ⚠ {err}
                </span>
              )}
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
                  NV có <b>BH đóng ở nơi khác</b> — công ty KHÔNG trừ
                  BHXH/BHYT/BHTN của NV.
                  <br />→ Công ty chỉ đóng <b>TNLĐ-BNN</b>{" "}
                  {pctOf(params.tnld_bnn_rate)}% ={" "}
                  <b>{money(bhBase * params.tnld_bnn_rate)}đ</b> (chi phí công
                  ty, không trừ vào lương NV).
                </>
              ) : (
                <>
                  Đóng BH trên lương cơ bản <b>{money(bhBase)}đ</b>, nhân viên
                  đóng gồm:
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
                          <span className="ns-badge ns-badge--ok">
                            Đang áp dụng
                          </span>
                        ) : s.effective_to == null ? (
                          <span className="ns-badge ns-badge--muted">
                            Sắp áp dụng
                          </span>
                        ) : (
                          <span className="ns-badge ns-badge--muted">
                            Đã thay
                          </span>
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

      {/* Đổi cách tính thuế = đổi TIỀN THUẾ của người này. Bỏ luỹ tiến là mất toàn bộ giảm trừ
          gia cảnh ⇒ thuế nhảy vọt. Bắt xác nhận, và nói bằng SỐ THẬT lấy từ cấu hình. */}
      <ConfirmDialog
        open={pitConfirm}
        danger={pitEff !== "luy_tien"}
        title="Đổi cách tính thuế TNCN của người này?"
        confirmLabel="Đổi và lưu"
        busy={busy}
        countdownSeconds={pitEff === "luy_tien" ? 0 : 3}
        onCancel={() => {
          if (!busy) setPitConfirm(false);
        }}
        onConfirm={() => void doSave()}
      >
        <p className="cdlg__msg">
          <b>{emp.full_name}</b> đang tính theo{" "}
          <b>{PIT_MODE_META[detail?.pit_mode ?? "luy_tien"].label}</b>, sẽ
          chuyển sang <b>{PIT_MODE_META[pitEff].label}</b>.
        </p>
        {pitEff === "khau_tru_10" && (
          <p className="cdlg__msg">
            Từ kỳ tính tới, người này <b>KHÔNG còn được giảm trừ gia cảnh</b>
            {params && (
              <>
                {" "}
                ({money(params.deduction_self)}đ bản thân
                {dependents > 0 && (
                  <>
                    {" "}
                    + {money(params.deduction_dependent * dependents)}đ cho{" "}
                    {dependents} người phụ thuộc
                  </>
                )}
                )
              </>
            )}
            {params && (
              <>
                {" "}
                mà bị khấu trừ thẳng <b>{pctOf(params.pit_flat_rate)}%</b> trên
                thu nhập chịu thuế (từ {money(params.pit_flat_threshold)}đ trở
                lên)
              </>
            )}
            . <b>Tiền thuế sẽ tăng vọt.</b> Chỉ chọn cho HĐ dưới 3 tháng / thời
            vụ / thực tập.
          </p>
        )}
        {pitEff === "cam_ket_08" && (
          <p className="cdlg__msg">
            Hệ thống sẽ <b>KHÔNG khấu trừ thuế TNCN</b> của người này. Chỉ chọn
            khi đã nhận đủ bản cam kết <b>08/CK-TNCN</b> — khai sai thì công ty
            chịu trách nhiệm khấu trừ thiếu.
          </p>
        )}
        {pitEff === "luy_tien" && (
          <p className="cdlg__msg">
            Người này quay lại tính theo{" "}
            <b>bảng thuế luỹ tiến + giảm trừ gia cảnh</b>
            {deductionTotal != null && (
              <> (tổng giảm trừ hiện tại {money(deductionTotal)}đ/tháng)</>
            )}
            .
          </p>
        )}
        <p className="cdlg__msg">
          Kỳ lương đã chốt/đã chi giữ nguyên số cũ; thay đổi chỉ ăn vào kỳ tính
          từ đây về sau.
        </p>
      </ConfirmDialog>
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

function TamUngTab({
  token,
  eventTick,
}: {
  token: string;
  eventTick?: number;
}) {
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
        <button
          className="btn btn--primary"
          onClick={() => setAdding("tam_ung")}
        >
          + Thêm ứng
        </button>
        <button
          className="btn btn--ghost"
          onClick={() => setAdding("luong_dot_1")}
        >
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
          ? [...r.items].sort((a, b) =>
              b.effective_from.localeCompare(a.effective_from),
            )[0]
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
            {isDot1 ? "Phiếu lương đợt 1" : "Thêm tạm ứng"} —{" "}
            {String(month).padStart(2, "0")}/{year}
          </h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          {isDot1 && (
            <p className="cc-note">
              Số tiền điền sẵn theo <b>“Lương trả 1 lần”</b> trong hồ sơ NV (sửa
              được). Duyệt phiếu xong mới trừ vào lương — hiện thành dòng{" "}
              <b>“Thanh toán lương đợt 1”</b> trên phiếu lương.
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

function PayslipCard({
  line: l,
  period,
}: {
  line: PayrollLine;
  period: PayrollPeriod;
}) {
  // 3 khoản phụ cấp KHAI TAY — mỗi khoản một dòng. BẪY CỘNG ĐÔI: `l.allowance` là TỔNG của
  // đúng 2 số (thâm niên + khác) → KHÔNG cộng `allowance` vào tổng thu nữa. Phụ cấp CA
  // (`ca_pay`, chính là `night_pay`) là khoản RIÊNG, nằm NGOÀI `allowance`.
  // Dòng lương cũ: khác = allowance, thâm niên = 0 → vẫn hiện đúng, không mất tiền.
  const pcCa = l.ca_pay ?? l.night_pay;
  const pcThamNien = l.phu_cap_tham_nien ?? 0;

  // Khoản DANH MỤC của dòng (Tầng 3). HAI NGUỒN, HAI CÁCH CỘNG — nhầm là sai tiền:
  //   `employee` = chép từ hồ sơ, ĐÃ NẰM TRONG `l.allowance` ⇒ tách thành dòng riêng thì phải
  //                TRỪ khỏi "Phụ cấp khác", không thì cộng đôi.
  //   `line`     = phát sinh riêng kỳ này, nằm NGOÀI `allowance` ⇒ cộng thẳng thành dòng mới.
  const comps = l.components ?? [];
  const compThuHoSo = comps.filter(
    (c) => c.kind !== "tru" && c.source === "employee",
  );
  const compThuKy = comps.filter(
    (c) => c.kind !== "tru" && c.source === "line",
  );
  const compTru = comps.filter((c) => c.kind === "tru");
  const pcKhacGoc = l.phu_cap_khac ?? l.allowance - pcThamNien;
  const pcKhac = Math.max(
    0,
    pcKhacGoc - compThuHoSo.reduce((s, c) => s + c.amount, 0),
  );
  const compLabel = (c: LineComponent) =>
    c.note ? `${c.name} (${c.note})` : c.name;

  // Dòng phụ "TRONG ĐÓ" — chỉ để NV đối chiếu, TUYỆT ĐỐI KHÔNG cộng vào TỔNG THU: số này đã
  // nằm sẵn trong `luong_cong` (ngày nghỉ phép chỉ trả LƯƠNG VỊ TRÍ, không có lương trách
  // nhiệm). Cùng idiom `phu_cap_tham_nien ⊂ allowance`; cộng nhầm là SAI TIỀN LƯƠNG.
  // Key = nhãn dòng cha → dòng phụ render ngay dưới dòng đó và nằm NGOÀI `incomeTotal`.
  const luongNgayPhep = l.luong_ngay_phep ?? 0;
  const incomeSub: Record<string, [string, number]> =
    luongNgayPhep > 0
      ? {
          "Lương theo công": [
            "Trong đó: lương ngày phép (theo lương vị trí)",
            luongNgayPhep,
          ],
        }
      : {};

  const income = [
    ["Lương theo công", l.luong_cong],
    // Hai khoản theo CA THỰC LÀM (từ 03/08/2026) — mỗi khoản MỘT DÒNG, không gộp: phiếu lương
    // phải nói rõ ăn bao nhiêu cơm, bao nhiêu phụ cấp.
    ["Cơm ca", l.meal_allowance_pay ?? 0],
    ["Phụ cấp ca (theo ca làm)", l.shift_allowance_pay ?? 0],
    // Ô cũ per-người đã ngưng ⇒ chỉ còn hiện ở kỳ CŨ đã chốt (còn số thì mới in dòng), để phiếu
    // lương tháng trước in lại vẫn đúng y nguyên.
    ...(pcCa ? ([["Phụ cấp ca (khai tay — đã ngưng)", pcCa]] as [string, number][]) : []),
    ["Phụ cấp ca đêm (giờ × hệ số)", l.night_premium_pay ?? 0],
    ["Phụ cấp thâm niên", pcThamNien],
    ["Phụ cấp khác", pcKhac],
    ["Chuyên cần", l.chuyen_can],
    ["Lương khoán / sản lượng", l.khoan],
    ["Tăng ca", l.ot_pay],
    // Khoản danh mục — mỗi khoản MỘT DÒNG, đúng tên chủ đặt (chữa "phụ cấp một cục").
    ...compThuHoSo.map((c) => [compLabel(c), c.amount]),
    ...compThuKy.map((c) => [compLabel(c), c.amount]),
    // Điều chỉnh lương (±) — cộng vào `gross` ở engine nên PHẢI có dòng, không thì tổng lệch.
    ...((l.dieu_chinh_luong ?? 0) !== 0
      ? [["Điều chỉnh lương", l.dieu_chinh_luong ?? 0]]
      : []),
    // 6 cột thưởng CŨ (ngừng ghi 28/07/2026) — chỉ hiện khi còn số, để kỳ đã chốt in y nguyên.
    ...legacyBonusRows(l),
  ] as [string, number][];
  const incomeTotal = income.reduce((s, [, v]) => s + v, 0);

  // BHXH/BHYT/BHTN: backend trả sẵn 3 dòng (nhãn đã kèm tỷ lệ) — AI XEM CŨNG THẤY, không phải đi xin
  // `GET /params` vốn đòi quyền cấu hình lương. Tổng 3 dòng luôn đúng bằng `l.bhxh` đã đóng băng.
  const deduct = [
    ...((l.insurance_lines ?? []).map((r) => [r.label, r.amount]) as [
      string,
      number,
    ][]),
    ["Công đoàn", l.cong_doan],
    ["Thuế TNCN", l.pit],
    ["Đi trễ / nghỉ KP", l.di_tre],
    ["Điện thoại vượt trội", l.dt_vuot_troi],
    ["Phạt biên bản", l.phat_bien_ban],
    ["Đồng phục / phạt 5S", l.phat_5s_dong_phuc],
    ["Giảm trừ khác", l.vi_pham],
    // Khoản danh mục loại TRỪ (mua đồng phục, ứng tiền…) — trừ thẳng vào thực nhận, KHÔNG thuộc
    // trần 30% Điều 102 (trần đó dành cho bồi thường/kỷ luật).
    ...compTru.map((c) => [compLabel(c), c.amount]),
    // 2 dòng RIÊNG: đợt 1 (đã trả giữa tháng qua phiếu) và tạm ứng ad-hoc. Thực nhận = đợt 2.
    ["Thanh toán lương đợt 1", l.luong_dot_1_total ?? 0],
    ["Tạm ứng đã nhận", l.advance_total],
  ] as [string, number][];
  const deductTotal = deduct.reduce((s, [, v]) => s + v, 0);

  return (
    <div className="lg-payslip2 lg-payslip-print">
      <div className="lg-payslip2__head">
        <div>
          <div className="lg-payslip2__title">PHIẾU LƯƠNG</div>
          <div className="lg-payslip2__who">
            {l.employee_name}{" "}
            <span className="ns__code">{l.employee_code}</span>
          </div>
          <div className="cc-card__hint">
            {l.department_name ?? "—"} · Tháng{" "}
            {String(period.month).padStart(2, "0")}/{period.year}
          </div>
        </div>
        <div className="lg-payslip2__meta">
          <div>
            NC chuẩn: <b>{l.standard_cong}</b> · Ngày công:{" "}
            <b>{l.actual_cong}</b>
          </div>
          <div>
            Giờ tăng ca: <b>{(l.ot_minutes / 60).toFixed(1)}h</b> · Mức đóng BH:{" "}
            <b>{money(l.insurance_base)}</b>
          </div>
          <span
            className={`ns-badge ${period.status !== "draft" ? "ns-badge--ok" : "ns-badge--muted"}`}
          >
            {period.status === "paid"
              ? "Đã chi"
              : period.status === "locked"
                ? "Đã chốt"
                : "Tạm tính"}
          </span>
        </div>
      </div>
      <div className="lg-payslip2__cols">
        <table className="lg-payslip2__tbl">
          <thead>
            <tr>
              <th>Các khoản THU</th>
              <th className="lg-num">Số tiền</th>
            </tr>
          </thead>
          <tbody>
            {income.map(([lbl, v]) => {
              const sub = incomeSub[lbl];
              return (
                <Fragment key={lbl}>
                  <tr>
                    <td>{lbl}</td>
                    <td className="lg-num">{v ? money(v) : "—"}</td>
                  </tr>
                  {sub && (
                    <tr className="lg-payslip2__in">
                      <td>{sub[0]}</td>
                      <td className="lg-num">{money(sub[1])}</td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
            <tr className="lg-payslip2__sub">
              <td>TỔNG THU</td>
              <td className="lg-num">{money(incomeTotal)}</td>
            </tr>
          </tbody>
        </table>
        <table className="lg-payslip2__tbl">
          <thead>
            <tr>
              <th>Các khoản TRỪ</th>
              <th className="lg-num">Số tiền</th>
            </tr>
          </thead>
          <tbody>
            {deduct.map(([lbl, v]) => (
              <tr key={lbl}>
                <td>{lbl}</td>
                <td className="lg-num">{v ? money(v) : "—"}</td>
              </tr>
            ))}
            <tr className="lg-payslip2__sub">
              <td>TỔNG TRỪ</td>
              <td className="lg-num">{money(deductTotal)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      {/* 2 dòng thuế (chủ 27/07/2026). `pit_taxable` là thu nhập TÍNH thuế — đã trừ bảo hiểm
          + giảm trừ gia cảnh, KHÔNG phải "tổng thu nhập chịu thuế"; backend không snapshot số
          đó nên gọi đúng tên, đừng dán nhãn "chịu thuế" lên số đã trừ giảm trừ. */}
      {/* <div className="lg-payslip2__tax">
        <span className="lg-payslip2__taxcell">
          <span>Thu nhập tính thuế TNCN</span>
          <b>{money(l.pit_taxable)}đ</b>
        </span>
        <span className="lg-payslip2__taxcell">
          <span>Thu nhập miễn thuế</span>
          <b>{money(l.thu_nhap_mien_thue)}đ</b>
        </span>
        <span className="lg-payslip2__taxnote">
          Thu nhập tính thuế = phần chịu thuế sau khi trừ bảo hiểm bắt buộc và
          giảm trừ gia cảnh — thuế TNCN bấm trên số này. Thu nhập miễn thuế gồm
          tăng ca, ca đêm và các khoản không tích “Chịu thuế” trong danh mục.
        </span>
      </div> */}
      <div className="lg-payslip2__net">
        <span>THỰC NHẬN</span>
        <span>{money(l.net_pay)}đ</span>
      </div>
      <div className="lg-payslip2__sign">
        <div>Người lập phiếu</div>
        <div>
          Người nhận tiền
          <br />
          <span className="cc-card__hint">(ký, ghi rõ họ tên)</span>
        </div>
      </div>
    </div>
  );
}

// --- Tab: Tạm ứng của tôi (self-service — nhân viên tự đề nghị) --------------

function TamUngCuaToiTab({
  token,
  eventTick,
}: {
  token: string;
  eventTick?: number;
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
        <button
          className="btn btn--primary"
          onClick={() => setAdding("tam_ung")}
        >
          + Đề nghị tạm ứng
        </button>
        <button
          className="btn btn--ghost"
          onClick={() => setAdding("luong_dot_1")}
        >
          + Xin lương đợt 1
        </button>
        <span className="cc-card__hint">
          Đề nghị gửi tới kế toán duyệt; bấm “In phiếu” để ký &amp; nộp.
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
                <th>Hành động</th>
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
  const [dateStr, setDateStr] = useState(() =>
    new Date().toISOString().slice(0, 10),
  );
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
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          {isDot1 && (
            <p className="cc-note">
              Số tiền điền sẵn theo <b>“Lương trả 1 lần”</b> trong hồ sơ của bạn
              — sửa được. Kế toán duyệt xong mới trừ, hiện thành dòng{" "}
              <b>“Thanh toán lương đợt 1”</b> trên phiếu lương.
              {dot1Prefill <= 0 && (
                <>
                  {" "}
                  Hồ sơ chưa khai mức này — nhập số bạn muốn ứng hoặc hỏi HCNS.
                </>
              )}
            </p>
          )}
          <div className="ns-grid">
            <label className="ns-field">
              <span className="ns-field__label">Kỳ lương</span>
              <input
                type="month"
                value={ym}
                onChange={(e) => setYm(e.target.value)}
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
            <label className="ns-field">
              <span className="ns-field__label">Số tiền *</span>
              <input
                type="number"
                min={0}
                value={amount}
                onChange={(e) => setAmount(Number(e.target.value))}
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
      <div
        className="lg-payslip-noprint"
        style={{ textAlign: "center", marginBottom: 8 }}
      >
        <button className="btn btn--ghost" onClick={() => window.print()}>
          🖨 In phiếu
        </button>
      </div>
      <PayslipCard line={l} period={data.period} />
    </div>
  );
}
