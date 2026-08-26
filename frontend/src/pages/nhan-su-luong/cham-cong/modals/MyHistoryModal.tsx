// Modal lịch sử chấm công của tôi (tách từ pages/ChamCongPage.tsx).
import { useMemo } from "react";
import type { AttendanceLog } from "../../../../api/client";
import {
  MapPin,
  Calendar,
  ClipboardList,
  LogIn,
  LogOut,
  Navigation,
} from "lucide-react";
import { isoToday } from "../shared/helpers";

function getLogDateKey(isoStr: string): string {
  try {
    const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(isoStr);
    const d = new Date(hasTz ? isoStr : `${isoStr}Z`);
    const todayStr = isoToday();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    const ymd = `${y}-${m}-${day}`;
    if (ymd === todayStr) return `Hôm nay (${day}/${m}/${y})`;
    return `${day}/${m}/${y}`;
  } catch {
    return "Khác";
  }
}

function getLogTimeOnly(isoStr: string): string {
  try {
    const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(isoStr);
    const d = new Date(hasTz ? isoStr : `${isoStr}Z`);
    return d.toLocaleTimeString("vi-VN", {
      timeZone: "Asia/Ho_Chi_Minh",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return isoStr;
  }
}

export function MyHistoryModal({
  logs,
  onClose,
}: {
  logs: AttendanceLog[];
  onClose: () => void;
}) {
  const totalCount = logs.length;
  const inCount = logs.filter((l) => l.check_type === "in").length;
  const outCount = logs.filter((l) => l.check_type === "out").length;

  const grouped = useMemo(() => {
    const map = new Map<string, AttendanceLog[]>();
    for (const log of logs) {
      const dateKey = getLogDateKey(log.checked_at);
      if (!map.has(dateKey)) map.set(dateKey, []);
      map.get(dateKey)!.push(log);
    }
    return Array.from(map.entries());
  }, [logs]);

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box cc-history-modal-box" style={{ maxWidth: "540px" }}>
        <header className="ns-modal__head cc-history-modal-head">
          <div className="cc-history-modal-title-group">
            <h2>
              <ClipboardList size={18} style={{ color: "var(--rust)" }} />
              <span>Lịch sử chấm công của tôi</span>
            </h2>
            <div className="cc-history-stats-strip">
              <span className="cc-history-stat-chip">
                Tổng: <b>{totalCount}</b> lượt
              </span>
              <span className="cc-history-stat-chip is-in">
                <LogIn size={11} /> VÀO: <b>{inCount}</b>
              </span>
              <span className="cc-history-stat-chip is-out">
                <LogOut size={11} /> RA: <b>{outCount}</b>
              </span>
            </div>
          </div>
          <button className="ns-modal__x" onClick={onClose} title="Đóng">
            ×
          </button>
        </header>

        <div
          className="ns-modal__body cc-history-modal-body"
          style={{ maxHeight: "420px", overflowY: "auto" }}
        >
          {grouped.length > 0 ? (
            <div className="cc-history-grouped-list">
              {grouped.map(([dateTitle, groupLogs]) => (
                <div key={dateTitle} className="cc-history-date-group">
                  <div className="cc-history-date-badge">
                    <Calendar size={12} />
                    <span>{dateTitle}</span>
                  </div>
                  <div className="cc-history-timeline">
                    {groupLogs.map((l) => {
                      const isIn = l.check_type === "in";
                      return (
                        <div key={l.id} className="cc-history-item">
                          <div className={`cc-history-dot ${isIn ? "is-in" : "is-out"}`} />
                          <div className="cc-history-card">
                            <div className="cc-history-card-left">
                              <div className={`cc-history-action-badge ${isIn ? "is-in" : "is-out"}`}>
                                {isIn ? <LogIn size={13} /> : <LogOut size={13} />}
                                <span>Chấm {isIn ? "VÀO" : "RA"}</span>
                              </div>
                              <div className="cc-history-location">
                                <MapPin size={12} />
                                <span>{l.location_name || "Vị trí không xác định"}</span>
                              </div>
                            </div>
                            <div className="cc-history-card-right">
                              <span className="cc-history-time">
                                {getLogTimeOnly(l.checked_at)}
                              </span>
                              {l.distance_m != null && (
                                <div className="cc-history-distance-chip">
                                  <Navigation size={10} />
                                  <span>Cự ly: {Math.round(l.distance_m)}m</span>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p
              className="ns__empty"
              style={{
                background: "var(--paper)",
                padding: "24px",
                borderRadius: "12px",
                border: "1px solid var(--rule-soft)",
                textAlign: "center",
              }}
            >
              Chưa có dữ liệu lịch sử chấm công.
            </p>
          )}
        </div>

        <footer className="ns-modal__foot cc-history-modal-foot">
          <button className="btn btn--primary" onClick={onClose} style={{ minWidth: "90px" }}>
            Đóng
          </button>
        </footer>
      </div>
    </div>
  );
}
