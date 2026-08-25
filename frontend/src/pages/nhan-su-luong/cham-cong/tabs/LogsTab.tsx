// Tab Nhật ký chấm công + bảng log (tách từ pages/ChamCongPage.tsx).
import { useEffect, useState } from "react";
import { api, type AttendanceLog, type TodayKpi } from "../../../../api/client";
import {
  UserCheck,
  MapPin,
  ClipboardList,
  FileEdit,
  XCircle,
  AlertTriangle,
  LogIn,
  LogOut,
  Search,
} from "lucide-react";
import { EmptyState } from "../../../../components/EmptyState";
import { MixDonut } from "../../../../components/charts";
import { getInitials } from "../shared/helpers";

// --- Tab: Bảng chấm công (HR) -----------------------------------------------

export function LogsTab({
  token,
  focusEmployeeId,
}: {
  token: string;
  focusEmployeeId?: number;
}) {
  const [items, setItems] = useState<AttendanceLog[] | null>(null);
  const [focus, setFocus] = useState<number | undefined>(focusEmployeeId);
  const [kpi, setKpi] = useState<TodayKpi | null>(null);

  useEffect(() => setFocus(focusEmployeeId), [focusEmployeeId]);

  // Ô tìm: gõ tới đâu gọi API tới đó thì mỗi phím một request. Chờ 300ms im tay rồi mới gọi.
  const [q, setQ] = useState("");
  const [qGui, setQGui] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQGui(q), 300);
    return () => clearTimeout(t);
  }, [q]);

  // Khoảng ngày để xem lại NGÀY TRƯỚC. Không đặt mặc định = hôm nay: mở màn ra thấy ngay lượt
  // gần nhất vẫn đúng ý hơn, ai cần lùi ngày thì tự chọn.
  const [tuNgay, setTuNgay] = useState("");
  const [denNgay, setDenNgay] = useState("");
  const ngayNguoc = !!tuNgay && !!denNgay && denNgay < tuNgay;

  useEffect(() => {
    if (ngayNguoc) return;      // khoảng vô nghĩa → giữ nguyên kết quả cũ, khỏi gọi API thừa
    api.attendance
      .logs(token, focus, qGui, tuNgay || undefined, denNgay || undefined)
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));
  }, [token, focus, qGui, tuNgay, denNgay, ngayNguoc]);

  useEffect(() => {
    if (focus == null) {
      api.attendance
        .kpi(token)
        .then(setKpi)
        .catch(() => setKpi(null));
    }
  }, [token, focus]);

  const focusName = focus
    ? items?.find((l) => l.employee_id === focus)?.employee_name
    : undefined;

  // Render chart slices for Recharts MixDonut
  const chartSlices = kpi
    ? [
        { label: "Đang có mặt", value: kpi.present_now },
        { label: "Quên chấm RA", value: kpi.missing_out },
        { label: "Đi muộn hôm nay", value: kpi.late_today },
        { label: "YC chờ duyệt", value: kpi.pending_requests },
      ].filter((s) => s.value > 0)
    : [];

  return (
    <div>
      {focus != null && (
        <div className="cc-focus">
          <span>
            Đang xem chấm công của <b>{focusName ?? `NV #${focus}`}</b>
          </span>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => setFocus(undefined)}
          >
            ✕ Bỏ lọc — xem cả xưởng
          </button>
        </div>
      )}

      {focus == null && kpi && (
        <div className="cc-analytics-section">
          <div className="cc-analytics-grid">
            {/* KPI Cards Grid */}
            <div className="cc-kpi-grid">
              <div className="cc-kpi-card cc-kpi-card--in">
                <div className="cc-kpi-icon-wrapper">
                  <UserCheck size={18} />
                </div>
                <div className="cc-kpi-info">
                  <span className="cc-kpi-num">{kpi.present_now}</span>
                  <span className="cc-kpi-title">Đang có mặt</span>
                </div>
              </div>
              <div className="cc-kpi-card cc-kpi-card--out">
                <div className="cc-kpi-icon-wrapper">
                  <XCircle size={18} />
                </div>
                <div className="cc-kpi-info">
                  <span className="cc-kpi-num">{kpi.missing_out}</span>
                  <span className="cc-kpi-title">Quên chấm RA</span>
                </div>
              </div>
              <div className="cc-kpi-card cc-kpi-card--late">
                <div className="cc-kpi-icon-wrapper">
                  <AlertTriangle size={18} />
                </div>
                <div className="cc-kpi-info">
                  <span className="cc-kpi-num">{kpi.late_today}</span>
                  <span className="cc-kpi-title">Đi muộn hôm nay</span>
                </div>
              </div>
              <div className="cc-kpi-card cc-kpi-card--pending">
                <div className="cc-kpi-icon-wrapper">
                  <FileEdit size={18} />
                </div>
                <div className="cc-kpi-info">
                  <span className="cc-kpi-num">{kpi.pending_requests}</span>
                  <span className="cc-kpi-title">YC chờ duyệt</span>
                </div>
              </div>
            </div>

            {/* Donut chart analysis */}
            <div
              style={{
                background: "var(--paper)",
                padding: "16px",
                borderRadius: "10px",
                border: "1px solid var(--rule-soft)",
              }}
            >
              <div className="cc-chart-title">
                <ClipboardList size={14} /> Tỷ lệ chuyên cần hôm nay
              </div>
              {chartSlices.length > 0 ? (
                <div className="cc-chart-container">
                  <MixDonut
                    slices={chartSlices}
                    centerTop={String(kpi.present_now)}
                    centerBottom="Đang có mặt"
                    formatValue={(v) => `${v} người`}
                    height={160}
                  />
                </div>
              ) : (
                <div
                  className="ns__empty"
                  style={{
                    height: "160px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  Hôm nay chưa có dữ liệu chấm công.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Dùng lại `cc-sp-search` của chính màn này (lưới Phân ca). KHÔNG mượn `lg-search-*` bên
          màn Lương: class đó nằm trong `luong.css` mà file này không import — mượn là ô trần
          không style, mà kéo cả `luong.css` sang thì tệ hơn nữa. */}
      <div className="cc-toolbar" style={{ marginBottom: 10, flexWrap: "wrap", gap: 8 }}>
        <label className="cc-sp-search">
          <Search size={14} />
          <input
            placeholder="Tìm theo tên / mã nhân viên…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        <label className="cc-sp-search">
          <span style={{ fontSize: 12 }}>Từ</span>
          <input
            type="date"
            value={tuNgay}
            max={denNgay || undefined}
            onChange={(e) => setTuNgay(e.target.value)}
          />
        </label>
        <label className="cc-sp-search">
          <span style={{ fontSize: 12 }}>đến</span>
          <input
            type="date"
            value={denNgay}
            min={tuNgay || undefined}
            onChange={(e) => setDenNgay(e.target.value)}
          />
        </label>
        {(tuNgay || denNgay) && (
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => {
              setTuNgay("");
              setDenNgay("");
            }}
          >
            ✕ Bỏ lọc ngày
          </button>
        )}
      </div>
      {ngayNguoc && (
        <div className="banner banner--error" style={{ marginBottom: 10 }}>
          Đến ngày phải sau hoặc bằng từ ngày.
        </div>
      )}

      {!items ? (
        <EmptyState trangThai="dang-tai" inline />
      ) : (
        <>
          <AttendanceTable logs={items} showEmployee={focus == null} />
          {/* Nói THẬT về giới hạn: không ghi thì người dùng tưởng đã thấy hết rồi kết luận sai
              ("hôm kia nó không chấm công") trong khi thật ra lượt cũ nằm ngoài 100 dòng này. */}
          <p className="cc-note" style={{ marginTop: 8 }}>
            {items.length === 0
              ? `Không có lượt chấm công nào${qGui ? ` khớp “${qGui}”` : ""}${
                  tuNgay || denNgay ? " trong khoảng ngày đã chọn" : ""
                }.`
              : tuNgay || denNgay
                ? `Đang xem ${items.length} lượt bấm trong khoảng ngày đã chọn${qGui ? ` khớp “${qGui}”` : ""}.`
                : `Đang xem ${items.length} lượt bấm gần nhất${qGui ? ` khớp “${qGui}”` : ""} — tối đa 100. Muốn xem ngày trước thì chọn khoảng ngày ở trên.`}
          </p>
        </>
      )}
    </div>
  );
}

// --- Shared table -----------------------------------------------------------

function parseDateTimeVN(iso: string | null | undefined) {
  if (!iso) return { time: "—", date: "" };
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso);
  const d = new Date(hasTz ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return { time: iso, date: "" };
  const timeStr = d.toLocaleTimeString("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh",
    hour12: false,
  });
  const dateStr = d.toLocaleDateString("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh",
  });
  return { time: timeStr, date: dateStr };
}

function AttendanceTable({
  logs,
  showEmployee,
}: {
  logs: AttendanceLog[];
  showEmployee: boolean;
}) {
  return (
    <div className="ns__tablewrap">
      <table className="ns__table cc-log-table">
        <thead>
          <tr>
            {showEmployee && <th>Nhân viên</th>}
            <th style={{ width: "120px" }}>Loại</th>
            <th style={{ width: "150px" }}>Thời gian</th>
            <th>Điểm chấm công</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((l) => {
            const { time, date } = parseDateTimeVN(l.checked_at);
            const isInside = l.distance_m == null || l.distance_m <= 150; // Bán kính chuẩn 150m
            return (
              <tr
                key={l.id}
                className={`cc-log-row cc-log-row--${l.check_type}`}
              >
                {showEmployee && (
                  <td>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "10px",
                      }}
                    >
                      <span className="cc-avatar-mini">
                        {getInitials(l.employee_name)}
                      </span>
                      <span
                        style={{
                          fontWeight: "var(--fw-medium)",
                          color: "var(--ink)",
                        }}
                      >
                        {l.employee_name ?? `NV#${l.employee_id}`}
                      </span>
                    </div>
                  </td>
                )}
                <td>
                  <span
                    className={`cc-log-badge cc-log-badge--${l.check_type}`}
                  >
                    {l.check_type === "in" ? (
                      <>
                        <LogIn size={12} style={{ marginRight: "4px" }} />
                        <span>VÀO</span>
                      </>
                    ) : (
                      <>
                        <LogOut size={12} style={{ marginRight: "4px" }} />
                        <span>RA</span>
                      </>
                    )}
                  </span>
                </td>
                <td>
                  <div style={{ display: "flex", flexDirection: "column" }}>
                    <span className="cc-log-time">{time}</span>
                    <span className="cc-log-date">{date}</span>
                  </div>
                </td>
                <td>
                  <div style={{ display: "flex", flexDirection: "column" }}>
                    <span
                      style={{
                        fontWeight: "var(--fw-medium)",
                        color: "var(--ink)",
                      }}
                    >
                      {l.location_name ?? "📍 Vị trí ngoài danh mục"}
                    </span>
                    <span
                      className={`cc-log-distance ${isInside ? "is-inside" : "is-outside"}`}
                    >
                      <MapPin
                        size={11}
                        style={{
                          marginRight: "3px",
                          display: "inline-block",
                          verticalAlign: "middle",
                        }}
                      />
                      {l.distance_m != null
                        ? isInside
                          ? `Trong phạm vi (${Math.round(l.distance_m)}m)`
                          : `Ngoài phạm vi (${Math.round(l.distance_m)}m)`
                        : "Không có GPS"}
                    </span>
                  </div>
                </td>
              </tr>
            );
          })}
          {logs.length === 0 && (
            <tr>
              <td colSpan={showEmployee ? 4 : 3} className="ns__empty">
                Chưa có bản ghi chấm công.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
