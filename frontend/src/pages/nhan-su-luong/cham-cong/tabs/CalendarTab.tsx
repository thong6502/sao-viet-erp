// Tab Lịch & Ngày lễ (tách từ pages/ChamCongPage.tsx).
import { useCallback, useEffect, useState } from "react";
import {
  api,
  type WorkCalendarConfig,
  type WorkCalendarConfigInput,
  type SpecialDay,
  type SpecialDaysOut,
  type CalendarMonth,
  type CalendarDayCell,
} from "../../../../api/client";
import {
  Trash2,
  Edit3,
  Plus,
  ChevronLeft,
  ChevronRight,
  Info,
} from "lucide-react";
import { SpecialDayForm } from "../modals/SpecialDayForm";
import { fmtDateVN } from "../shared/helpers";

// --- Tab: Lịch làm việc & Ngày lễ (nền dùng chung cho Công / Phép / Lương) --

const WEEKDAY_FIELDS: { key: keyof WorkCalendarConfigInput; label: string }[] =
  [
    { key: "works_mon", label: "T2" },
    { key: "works_tue", label: "T3" },
    { key: "works_wed", label: "T4" },
    { key: "works_thu", label: "T5" },
    { key: "works_fri", label: "T6" },
    { key: "works_sat", label: "T7" },
    { key: "works_sun", label: "CN" },
  ];
const KIND_LABEL: Record<string, string> = {
  off: "Nghỉ lễ",
  work: "Làm bù",
  off1x: "Nghỉ — làm 1×",
};

/** Lưới tháng: chèn ô trống đầu tuần để ngày 1 rơi đúng cột thứ (Mon=0..Sun=6). */
function buildMonthGrid(m: CalendarMonth): (CalendarDayCell | null)[] {
  const lead = m.days.length ? m.days[0].weekday : 0;
  return [...Array<null>(lead).fill(null), ...m.days];
}

export function CalendarTab({ token }: { token: string }) {
  const now = new Date();
  const [config, setConfig] = useState<WorkCalendarConfig | null>(null);
  const [cfgBusy, setCfgBusy] = useState(false);
  const [cfgMsg, setCfgMsg] = useState<string | null>(null);
  const [year, setYear] = useState(now.getFullYear());
  const [special, setSpecial] = useState<SpecialDaysOut | null>(null);
  const [editing, setEditing] = useState<SpecialDay | "new" | null>(null);
  const [previewMonth, setPreviewMonth] = useState(now.getMonth() + 1);
  const [preview, setPreview] = useState<CalendarMonth | null>(null);

  const loadConfig = useCallback(() => {
    api.calendar
      .getConfig(token)
      .then(setConfig)
      .catch(() => setConfig(null));
  }, [token]);
  const loadSpecial = useCallback(() => {
    api.calendar
      .specialDays(token, year)
      .then(setSpecial)
      .catch(() => setSpecial(null));
  }, [token, year]);
  const loadPreview = useCallback(() => {
    api.calendar
      .month(token, year, previewMonth)
      .then(setPreview)
      .catch(() => setPreview(null));
  }, [token, year, previewMonth]);
  useEffect(() => {
    loadConfig();
  }, [loadConfig]);
  useEffect(() => {
    loadSpecial();
  }, [loadSpecial]);
  useEffect(() => {
    loadPreview();
  }, [loadPreview]);

  function toggleDay(key: keyof WorkCalendarConfigInput) {
    setConfig((c) => (c ? { ...c, [key]: !c[key] } : c));
    setCfgMsg(null);
  }
  async function saveConfig() {
    if (!config) return;
    setCfgBusy(true);
    setCfgMsg(null);
    try {
      const saved = await api.calendar.updateConfig(token, {
        works_mon: config.works_mon,
        works_tue: config.works_tue,
        works_wed: config.works_wed,
        works_thu: config.works_thu,
        works_fri: config.works_fri,
        works_sat: config.works_sat,
        works_sun: config.works_sun,
      });
      setConfig(saved);
      setCfgMsg("Đã lưu tuần làm việc.");
      loadPreview();
    } catch (e) {
      setCfgMsg(e instanceof Error ? e.message : "Lỗi khi lưu.");
    } finally {
      setCfgBusy(false);
    }
  }
  async function removeSpecial(id: number) {
    await api.calendar.deleteSpecialDay(token, id);
    loadSpecial();
    loadPreview();
  }

  return (
    <div className="cal">
      <div className="cal-grid-top">
        {/* Tuần làm việc chuẩn */}
        <section className="cal-panel">
          <h4 className="ns-section__title">Tuần làm việc chuẩn</h4>
          <p className="cc-note" style={{ marginTop: "4px" }}>
            Bật/tắt từng thứ. Ngày làm việc là mẫu tính công chuẩn tháng + trừ
            phép năm; ngày tắt = nghỉ tuần (không trừ phép). Ngày lễ khai riêng
            ở bên cạnh.
          </p>
          <div className="cal-week">
            {WEEKDAY_FIELDS.map((w) => (
              <label
                key={String(w.key)}
                className={`cal-week__day ${config?.[w.key] ? "is-on" : ""}`}
              >
                <input
                  type="checkbox"
                  checked={!!config?.[w.key]}
                  onChange={() => toggleDay(w.key)}
                />
                <span>{w.label}</span>
              </label>
            ))}
          </div>
          <div
            className="cc-toolbar"
            style={{ marginTop: "auto", marginBottom: 0 }}
          >
            <button
              className="btn btn--primary"
              onClick={saveConfig}
              disabled={cfgBusy || !config}
            >
              {cfgBusy ? "Đang lưu…" : "Lưu tuần làm việc"}
            </button>
            {cfgMsg && (
              <span
                className="cc-assign__msg"
                style={{
                  marginLeft: "12px",
                  color: "var(--moss)",
                  fontSize: "13px",
                }}
              >
                {cfgMsg}
              </span>
            )}
          </div>
        </section>

        {/* Ngày lễ & làm bù */}
        <section
          className="cal-panel"
          style={{ display: "flex", flexDirection: "column" }}
        >
          <div className="cal-panel__head">
            <h4 className="ns-section__title">Ngày lễ & làm bù</h4>
            <div className="cal-yearpick">
              <button
                type="button"
                onClick={() => setYear((y) => y - 1)}
                aria-label="Năm trước"
              >
                <ChevronLeft size={16} />
              </button>
              <span className="cal-year">{year}</span>
              <button
                type="button"
                onClick={() => setYear((y) => y + 1)}
                aria-label="Năm sau"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>

          <div className="cc-toolbar">
            <button
              className="btn btn--primary"
              onClick={() => setEditing("new")}
            >
              <Plus
                size={14}
                style={{
                  marginRight: "4px",
                  display: "inline-block",
                  verticalAlign: "middle",
                }}
              />
              <span>Thêm ngày</span>
            </button>
          </div>

          <div
            className="ns__tablewrap"
            style={{ flexGrow: 1, overflowY: "auto", maxHeight: "250px" }}
          >
            <table className="ns__table">
              <thead>
                <tr>
                  <th>Ngày</th>
                  <th>Tên</th>
                  <th>Loại</th>
                  <th>Hưởng lương</th>
                  <th style={{ width: "160px", textAlign: "right" }}></th>
                </tr>
              </thead>
              <tbody>
                {special?.items.map((s) => (
                  <tr key={s.id}>
                    <td className="ns__code">{fmtDateVN(s.day)}</td>
                    <td style={{ fontWeight: "var(--fw-medium)" }}>{s.name}</td>
                    <td>
                      <span
                        className={`ns-badge ${s.kind === "work" ? "ns-badge--info" : s.kind === "off1x" ? "ns-badge--warn" : "ns-badge--ok"}`}
                      >
                        {KIND_LABEL[s.kind] ?? s.kind}
                      </span>
                    </td>
                    <td>
                      {s.kind === "off" ? (s.is_paid ? "Có" : "Không") : "—"}
                    </td>
                    <td className="cc-rowact" style={{ textAlign: "right" }}>
                      <button
                        className="btn btn--ghost btn--sm"
                        onClick={() => setEditing(s)}
                        style={{ padding: "4px 8px", marginRight: "4px" }}
                        title="Sửa"
                      >
                        <Edit3
                          size={13}
                          style={{
                            display: "inline-block",
                            verticalAlign: "middle",
                            marginRight: "2px",
                          }}
                        />
                        Sửa
                      </button>
                      <button
                        className="btn btn--ghost btn--sm ns-danger"
                        onClick={() => removeSpecial(s.id)}
                        style={{ padding: "4px 8px" }}
                        title="Xóa"
                      >
                        <Trash2
                          size={13}
                          style={{
                            display: "inline-block",
                            verticalAlign: "middle",
                            marginRight: "2px",
                          }}
                        />
                        Xóa
                      </button>
                    </td>
                  </tr>
                ))}
                {!special && (
                  <tr>
                    <td colSpan={5} className="ns__empty">
                      Đang tải…
                    </td>
                  </tr>
                )}
                {special?.items.length === 0 && (
                  <tr>
                    <td colSpan={5} className="ns__empty">
                      Chưa khai ngày đặc biệt nào cho năm {year}.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {/* Xem trước tháng (Full Width) */}
      <section className="cal-panel">
        <div className="cal-panel__head">
          <h4 className="ns-section__title">Xem trước tháng</h4>
          <div className="cal-monthpick-nav">
            <button
              type="button"
              onClick={() => setPreviewMonth((m) => (m === 1 ? 12 : m - 1))}
              aria-label="Tháng trước"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="cal-month-label">Tháng {previewMonth}</span>
            <button
              type="button"
              onClick={() => setPreviewMonth((m) => (m === 12 ? 1 : m + 1))}
              aria-label="Tháng sau"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
        {!preview && <p className="cal-standard">Đang tải lịch tháng…</p>}
        {preview && (
          <>
            <p className="cal-standard">
              <Info size={14} style={{ color: "var(--ash)", flexShrink: 0 }} />
              <span>
                Công chuẩn tháng {preview.month}/{preview.year}:{" "}
                <strong>{preview.working_days}</strong> công
                {preview.holidays.length > 0 && (
                  <> · {preview.holidays.length} ngày lễ</>
                )}
              </span>
            </p>
            <div className="cc-month-grid">
              {["T2", "T3", "T4", "T5", "T6", "T7", "CN"].map((d) => (
                <div
                  key={d}
                  style={{
                    textAlign: "center",
                    fontWeight: "bold",
                    fontSize: "12px",
                    paddingBottom: "6px",
                    color: "var(--ash)",
                  }}
                >
                  {d}
                </div>
              ))}
              {buildMonthGrid(preview).map((cell, i) =>
                cell ? (
                  <div
                    key={i}
                    className={`cc-month-cell cc-month-cell--${cell.kind}`}
                    title={cell.name ?? ""}
                  >
                    <span className="cc-month-cell-num">{cell.day}</span>
                    {cell.name && (
                      <span className="cc-month-cell-name">{cell.name}</span>
                    )}
                  </div>
                ) : (
                  <div key={i} className="cc-month-cell cc-month-cell--empty" />
                ),
              )}
            </div>
            <div className="cal-legend">
              <span className="cal-lg cal-lg--work">Ngày làm</span>
              <span className="cal-lg cal-lg--weekend">Nghỉ tuần</span>
              <span className="cal-lg cal-lg--holiday">Nghỉ lễ</span>
              <span className="cal-lg cal-lg--makeup">Làm bù</span>
            </div>
          </>
        )}
      </section>

      {editing && (
        <SpecialDayForm
          token={token}
          special={editing === "new" ? null : editing}
          year={year}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            loadSpecial();
            loadPreview();
          }}
        />
      )}
    </div>
  );
}
