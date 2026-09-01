// Tab Công của tôi (tách từ pages/ChamCongPage.tsx).
import { useCallback, useEffect, useState } from "react";
import {
  api,
  type AdjustQuota,
  type AdjustRequest,
  type Timesheet,
  type ShiftChange,
} from "../../../../api/client";
import { CalendarDays, ChevronLeft, ChevronRight, Info } from "lucide-react";
import { EmptyState } from "../../../../components/EmptyState";
import { statusBadge } from "../components/badges";
import { RequestAdjustModal } from "../modals/RequestAdjustModal";
import { HE_SO_NGAY_MAC_DINH } from "../shared/constants";
import { docONgay, fmtDateTime, fmtDateVN } from "../shared/helpers";

// --- Tab: Công của tôi (self-service timesheet) -----------------------------

export function MyTimesheetTab({ token }: { token: string }) {
  const [ym, setYm] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });
  const [data, setData] = useState<Timesheet | null>(null);
  const [loading, setLoading] = useState(true);
  const [reqs, setReqs] = useState<AdjustRequest[]>([]);
  const [quota, setQuota] = useState<AdjustQuota | null>(null);
  const [reqDate, setReqDate] = useState<string | null>(null); // ngày đang xin chỉnh (mở modal)
  const [year, month] = ym.split("-").map(Number);

  const taiBieuCong = useCallback(() => {
    setLoading(true);
    api.attendance
      .myTimesheet(token, year, month)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [token, year, month]);

  useEffect(() => {
    taiBieuCong();
  }, [taiBieuCong]);

  const loadReqs = useCallback(() => {
    api.attendance
      .myAdjustRequests(token)
      .then((r) => {
        setReqs(r.items);
        setQuota(r.quota ?? null);
      })
      .catch(() => {
        setReqs([]);
        setQuota(null);
      });
  }, [token]);
  useEffect(() => {
    loadReqs();
  }, [loadReqs]);

  // Hộp thư "ca của tôi vừa bị đổi" — CHỈ tin CHƯA ĐỌC.
  //
  // Mở màn = đánh dấu đã đọc (badge về 0) nhưng khối vẫn HIỆN hết lượt này, để người ta kịp
  // đọc; lần vào sau mới hết. Lấy cả tin đã đọc thì khối bám đầu màn vĩnh viễn — lỗi đã gặp.
  // Dài thì gập lại: 50 thông báo mà đổ hết ra là đẩy bảng công xuống dưới màn hình.
  const [shiftMsgs, setShiftMsgs] = useState<ShiftChange[]>([]);
  const [msgsOpen, setMsgsOpen] = useState(false);   // mở rộng xem hết
  const [msgsHidden, setMsgsHidden] = useState(false);
  useEffect(() => {
    let alive = true;
    api.attendance
      .myShiftChanges(token, { unseen: true })
      .then((r) => {
        if (!alive) return;
        setShiftMsgs(r.items);
        if (r.items.length > 0) {
          void api.attendance.markShiftChangesSeen(token).catch(() => {});
        }
      })
      .catch(() => alive && setShiftMsgs([]));
    return () => {
      alive = false;
    };
  }, [token]);
  const MSG_PREVIEW = 3;
  const msgsShown = msgsOpen ? shiftMsgs : shiftMsgs.slice(0, MSG_PREVIEW);

  // Ngày CHƯA TỚI không xin chỉnh công được — đơn này nghĩa là "tôi quên chấm hôm đó", không ai
  // quên một ngày chưa xảy ra. Backend đã chặn (`_require_not_future`); ở đây chặn trước để khỏi
  // mời người ta bấm rồi mới báo đỏ.
  const homNay = new Date();
  homNay.setHours(0, 0, 0, 0);
  function laTuongLai(dayNum: number) {
    return new Date(year, month - 1, dayNum) > homNay;
  }

  function openReq(dayNum: number) {
    if (laTuongLai(dayNum)) return;
    setReqDate(
      `${year}-${String(month).padStart(2, "0")}-${String(dayNum).padStart(2, "0")}`,
    );
  }

  function shiftMonth(offset: number) {
    const [curY, curM] = ym.split("-").map(Number);
    const d = new Date(curY, curM - 1 + offset, 1);
    setYm(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }

  const row = data?.rows[0] ?? null;
  // Hệ số quy đổi công lễ / nghỉ tuần — LẤY TỪ MÁY CHỦ (khai ở Cấu hình lương), không viết cứng.
  const heSoNgay = data?.he_so_ngay ?? HE_SO_NGAY_MAC_DINH;

  // Build calendar matrix cells
  const startOffset = (new Date(year, month - 1, 1).getDay() + 6) % 7; // Mon=0..Sun=6
  const calendarCells: (number | null)[] = [];
  for (let i = 0; i < startOffset; i++) {
    calendarCells.push(null);
  }
  if (data) {
    for (let d = 1; d <= data.days_in_month; d++) {
      calendarCells.push(d);
    }
  }

  return (
    <div>
      {/* Ca bị quản lý đổi — người lao động phải biết, không phải tự phát hiện lúc tới xưởng. */}
      {shiftMsgs.length > 0 && !msgsHidden && (
        <div className="cc-myshift">
          <div className="cc-myshift__bar">
            <span className="cc-myshift__head">
              🔔 Ca làm việc của bạn vừa được thay đổi
              {shiftMsgs.length > 1 && ` (${shiftMsgs.length})`}
            </span>
            <button
              type="button"
              className="cc-myshift__x"
              onClick={() => setMsgsHidden(true)}
              aria-label="Ẩn thông báo"
              title="Đã đọc, ẩn đi"
            >
              ×
            </button>
          </div>
          <ul className={`cc-myshift__list${msgsOpen ? " is-open" : ""}`}>
            {msgsShown.map((m) => (
              <li key={m.id}>
                Ca làm việc ngày <b>{fmtDateVN(m.apply_date)}</b>
                {m.kind === "base" && " (và các ngày sau)"} của bạn đã được thay đổi từ{" "}
                <b>{m.is_off_before ? "Nghỉ theo lịch" : (m.shift_name_before ?? "không có ca")}</b>{" "}
                sang{" "}
                <b>{m.is_off_after ? "Nghỉ theo lịch" : (m.shift_name_after ?? "không có ca")}</b>
                {m.actor_name && <> bởi <b>{m.actor_name}</b></>}.
                <em>{fmtDateTime(m.created_at)}</em>
              </li>
            ))}
          </ul>
          {shiftMsgs.length > MSG_PREVIEW && (
            <button
              type="button"
              className="cc-myshift__more"
              onClick={() => setMsgsOpen((o) => !o)}
            >
              {msgsOpen
                ? "Thu gọn"
                : `Xem thêm ${shiftMsgs.length - MSG_PREVIEW} thay đổi nữa`}
            </button>
          )}
        </div>
      )}
      <div className="cc-ts-toolbar-container">
        <div className="cc-month-navigator">
          <button
            className="cc-month-nav-btn"
            onClick={() => shiftMonth(-1)}
            title="Tháng trước"
          >
            <ChevronLeft size={16} />
          </button>
          <span className="cc-month-nav-label">
            Tháng {month} / {year}
          </span>
          <button
            className="cc-month-nav-btn"
            onClick={() => shiftMonth(1)}
            title="Tháng sau"
          >
            <ChevronRight size={16} />
          </button>
          <div className="cc-month-picker-wrapper">
            <input
              type="month"
              className="cc-month-picker-hidden"
              value={ym}
              onChange={(e) => setYm(e.target.value)}
              id="cc-month-picker"
            />
            <label
              htmlFor="cc-month-picker"
              className="cc-month-picker-trigger"
              title="Chọn tháng nhanh"
            >
              <CalendarDays size={14} /> Chọn tháng
            </label>
          </div>
        </div>

        <div className="cc-ts-info-group">
          <div className="cc-ts-legend">
            <span className="cc-ts-legend-title">Chú giải:</span>
            <span className="cc-badge-pill cc-badge-pill--primary">
              ✓ Đi làm
            </span>
            <span className="cc-badge-pill cc-badge-pill--orange">
              +OT Làm thêm
            </span>
            <span className="cc-badge-pill cc-badge-pill--purple">
              Nghỉ lễ/Phép
            </span>
          </div>

          <div className="cc-ts-tip">
            <Info size={13} style={{ color: "var(--rust)" }} />
            <span>Bấm vào ô ngày trên lịch để gửi yêu cầu chỉnh công.</span>
          </div>
        </div>
      </div>
      {loading && <EmptyState trangThai="dang-tai" inline />}
      {!loading && !data && (
        <EmptyState
          trangThai="loi"
          loi="Không tải được biểu công tháng này."
          onThuLai={taiBieuCong}
          inline
        />
      )}
      {/* Có `data` mà không có hàng: từ 31/07/2026 backend luôn trả hàng của chính người đăng nhập
          (kể cả chưa chấm buổi nào) nên nhánh này gần như không còn xảy ra. Giữ làm lưới an toàn —
          màn trắng trơn không một lời nào là thứ tệ nhất. */}
      {!loading && data && !row && (
        <EmptyState
          icon="calendar"
          title="Tháng này bạn chưa có dữ liệu chấm công"
          sub="Bấm vào ô ngày trên lịch để gửi yêu cầu chỉnh công."
          inline
        />
      )}
      {!loading && row && data && (
        <div
          style={{
            background: "var(--canvas)",
            padding: "20px",
            borderRadius: "10px",
            border: "1px solid var(--rule-soft)",
            boxShadow: "var(--shadow-1)",
          }}
        >
          <h4 className="ns-section__title" style={{ marginTop: 0 }}>
            Lịch công của tôi ({month}/{year})
          </h4>
          {/* Lịch vẫn hiện đủ tháng — dòng này chỉ nói thêm cho khỏi hiểu nhầm là mất dữ liệu.
              Trước đây cả lịch bị thay bằng một câu "chưa có dữ liệu", nên người quên chấm không
              còn ô ngày nào để bấm xin chỉnh công. */}
          {row.total_days === 0 && (
            <p className="cc-note" style={{ marginBottom: 12 }}>
              Tháng này bạn chưa có lượt chấm công nào. Bấm vào ô ngày để gửi yêu cầu chỉnh công.
            </p>
          )}

          <div className="cc-month-grid">
            {["T2", "T3", "T4", "T5", "T6", "T7", "CN"].map((w) => (
              <div
                key={w}
                style={{
                  textAlign: "center",
                  fontWeight: "bold",
                  fontSize: "12px",
                  paddingBottom: "8px",
                  color: "var(--ash)",
                }}
              >
                {w}
              </div>
            ))}
            {calendarCells.map((dayNum, idx) => {
              if (dayNum === null)
                return (
                  <div
                    key={`empty-${idx}`}
                    className="cc-month-cell cc-month-cell--empty"
                  />
                );
              const day = row.days[String(dayNum)];
              // Đọc ô qua `docONgay` — CHUNG với lịch NV bên màn HCNS, xem chú thích ở hàm đó.
              const o = docONgay(day, heSoNgay);
              let cellClass = "cc-month-cell" + o.variant;

              const currentDayOfWeek = new Date(
                year,
                month - 1,
                dayNum,
              ).getDay();
              const isWeekend =
                currentDayOfWeek === 0 || currentDayOfWeek === 6;
              if (!day && isWeekend) {
                cellClass += " cc-month-cell--weekend";
              }

              const chuaToi = laTuongLai(dayNum);
              return (
                <div
                  key={dayNum}
                  className={cellClass}
                  style={{
                    cursor: chuaToi ? "default" : "pointer",
                    opacity: chuaToi ? 0.5 : undefined,
                  }}
                  title={
                    chuaToi
                      ? "Ngày chưa tới — chỉ xin chỉnh công cho ngày đã qua hoặc hôm nay."
                      : "Bấm để gửi yêu cầu chỉnh công"
                  }
                  onClick={() => openReq(dayNum)}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <span className="cc-month-cell-num">{dayNum}</span>
                    <span className="cc-month-cell__pills">
                      {o.pills.map((p) => (
                        <span
                          key={p.text}
                          className={`cc-badge-pill cc-badge-pill--cell cc-badge-pill--${p.tone}`}
                          title={p.title}
                        >
                          {p.text}
                        </span>
                      ))}
                    </span>
                  </div>
                  {/* Tên CA của ngày (Phân ca tháng) — hiện DÙ có bấm hay không. Chủ hỏi
                      "điền ca từng ngày vào ô công". Bấm ô để đổi ca ở tab Khai ca. */}
                  {o.caLabel && (
                    <div className="cc-month-cell__ca" title={`Ca làm: ${o.caLabel}`}>
                      {o.caLabel}
                    </div>
                  )}
                  <div
                    style={{
                      fontSize: "12px",
                      fontWeight: 600,
                      color: "var(--ink)",
                      marginTop: "4px",
                    }}
                  >
                    {o.timeRange || "—"}
                  </div>
                  <div
                    style={{
                      fontSize: "12px",
                      color: "var(--ash)",
                      marginTop: "2px",
                      display: "flex",
                      // Dòng này dài hẳn ra từ 18/08/2026 ("Công: 1 → tính 4 công"), mà ô lịch
                      // chỉ rộng ~150px ở laptop ⇒ phải cho xuống dòng, không thì tràn ra ngoài.
                      flexWrap: "wrap",
                      gap: "2px",
                      justifyContent: "space-between",
                      width: "100%",
                    }}
                  >
                    <span>
                      {o.statusLabel}
                      {/* Chữ nằm THẲNG trên ô, không nhét vào tooltip: `title` của ô đã bị câu
                          "Bấm để gửi yêu cầu chỉnh công" chiếm, mà đây mới là thứ người ta cần
                          thấy ngay — "làm ngày lễ mà chỉ thấy Công: 1" chính là chỗ mất niềm tin. */}
                      {o.gain && <span className={o.gainClass}> {o.gain}</span>}
                    </span>
                    {day?.late && (
                      <span
                        style={{ color: "var(--signal)", fontWeight: "bold" }}
                      >
                        Muộn
                      </span>
                    )}
                    {day?.early && (
                      <span
                        style={{
                          color: "var(--amber-deep)",
                          fontWeight: "bold",
                        }}
                      >
                        Sớm
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {reqs.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <h4 className="ns-section__title">
            Yêu cầu chỉnh công đã gửi
            {quota && quota.limit > 0 && (
              <span
                className="cc-note"
                style={{ marginLeft: 8, fontWeight: 400 }}
              >
                · tháng {quota.month}: {quota.used}/{quota.limit} ngày, còn{" "}
                {quota.remaining} lần
              </span>
            )}
          </h4>
          <div className="ns__tablewrap">
            <table className="ns__table">
              <thead>
                <tr>
                  <th>Ngày</th>
                  <th>Chấm</th>
                  <th>Giờ đề xuất</th>
                  <th>Lý do</th>
                  <th>Trạng thái</th>
                  <th>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {reqs.map((r) => (
                  <tr key={r.id}>
                    <td>{r.work_date}</td>
                    <td>{r.check_type === "in" ? "VÀO" : "RA"}</td>
                    <td>{r.suggested_time ?? "—"}</td>
                    <td>
                      {r.reason}
                      {r.decision_note ? ` · (${r.decision_note})` : ""}
                    </td>
                    <td>{statusBadge(r.status)}</td>
                    <td>
                      {r.status === "pending" && (
                        <button
                          className="btn btn--ghost ns-danger"
                          style={{ padding: "2px 8px" }}
                          onClick={() =>
                            api.attendance
                              .cancelAdjustRequest(token, r.id)
                              .then(loadReqs)
                          }
                        >
                          Hủy
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {reqDate && (
        <RequestAdjustModal
          token={token}
          date={reqDate}
          quota={quota}
          onClose={() => setReqDate(null)}
          onSaved={() => {
            setReqDate(null);
            loadReqs();
          }}
        />
      )}
    </div>
  );
}
