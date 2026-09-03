import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronLeft, ChevronRight, Repeat, RotateCcw, X } from "lucide-react";
import { api, ApiError, type CareOccurrence } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import "./care-calendar.css";

const WD = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function mondayIdx(jsDay: number): number {
  return (jsDay + 6) % 7; // JS 0=CN → 6, 1=T2 → 0
}
function pillClass(o: CareOccurrence): string {
  if (o.status === "done") return "cc__pill cc__pill--done";
  if (o.status === "cancelled") return "cc__pill cc__pill--cancelled";
  if (o.remind_level >= 2) return "cc__pill cc__pill--late";
  if (o.remind_level === 1) return "cc__pill cc__pill--due";
  return "cc__pill cc__pill--future";
}
const recurring = (o: CareOccurrence) => o.repeat_freq !== "none";
const freqLabel = (f: string) => (f === "day" ? "ngày" : f === "week" ? "tuần" : "tháng");

/** Lịch hẹn chăm sóc kiểu Google Calendar (redesign-lich-hen-cham-soc). Một khái niệm duy nhất =
 * HẸN: bấm ô ngày → popover NEO TẠI Ô để đặt hẹn (lặp được); TICK tròn trên thẻ = xong + gạch ngang
 * (bấm lại = mở lại); KÉO thẻ hẹn sang ô khác = dời. Việc đã xong ở lại lịch làm bằng chứng. */
export function CareCalendar({ customerId, onChange }: { customerId: number; onChange?: () => void }) {
  const { token } = useAuth();
  const canUpdate = useCan()("khach_hang", "update");
  const today = useMemo(() => new Date(), []);
  const todayStr = ymd(today);

  const [ym, setYm] = useState<{ y: number; m: number }>({ y: today.getFullYear(), m: today.getMonth() });
  const [occ, setOcc] = useState<CareOccurrence[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Popover neo tại ô. formDay = đặt hẹn cho ngày đó; sel = xem/thao tác 1 thẻ hẹn.
  const [formDay, setFormDay] = useState<string | null>(null);
  const [fNote, setFNote] = useState("");
  const [fTime, setFTime] = useState("09:00");
  const [fFreq, setFFreq] = useState("none");
  const [fEvery, setFEvery] = useState(1);
  const [fUntil, setFUntil] = useState("");
  const [sel, setSel] = useState<CareOccurrence | null>(null);
  const [reDate, setReDate] = useState("");

  // Vị trí neo popover (px, tương đối với lưới) + kéo-thả.
  const [pop, setPop] = useState<{ left: number; top: number; above: boolean } | null>(null);
  const [dropDay, setDropDay] = useState<string | null>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<CareOccurrence | null>(null);

  const first = useMemo(() => new Date(ym.y, ym.m, 1), [ym]);
  const last = useMemo(() => new Date(ym.y, ym.m + 1, 0), [ym]);
  const from = ymd(first);
  const to = ymd(last);

  const load = useCallback(() => {
    if (!token) return;
    api.customers
      .careCalendar(token, customerId, from, to)
      .then((r) => { setOcc(r.items); setErr(null); })
      .catch(() => setErr("Không tải được lịch chăm sóc."));
  }, [token, customerId, from, to]);

  useEffect(() => { setOcc(null); setSel(null); setFormDay(null); setPop(null); load(); }, [load]);

  const closePop = useCallback(() => { setFormDay(null); setSel(null); setPop(null); }, []);

  // Click ra ngoài / Esc / đổi kích thước → đóng popover (đúng cảm giác Google Calendar).
  useEffect(() => {
    if (!formDay && !sel) return;
    function onDown(e: MouseEvent) {
      if (popRef.current && !popRef.current.contains(e.target as Node)) closePop();
    }
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") closePop(); }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", closePop);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", closePop);
    };
  }, [formDay, sel, closePop]);

  const byDay = useMemo(() => {
    const map: Record<string, CareOccurrence[]> = {};
    (occ ?? []).forEach((o) => {
      const k = o.due_date.slice(0, 10);
      (map[k] ??= []).push(o);
    });
    return map;
  }, [occ]);

  const cells = useMemo(() => {
    const lead = mondayIdx(first.getDay());
    const days = last.getDate();
    const out: (Date | null)[] = [];
    for (let i = 0; i < lead; i++) out.push(null);
    for (let dd = 1; dd <= days; dd++) out.push(new Date(ym.y, ym.m, dd));
    while (out.length % 7 !== 0) out.push(null);
    return out;
  }, [first, last, ym]);

  function move(delta: number) {
    closePop();
    setYm((s) => {
      const d = new Date(s.y, s.m + delta, 1);
      return { y: d.getFullYear(), m: d.getMonth() };
    });
  }

  // Neo popover vào 1 phần tử: mở xuống dưới, hoặc lên trên nếu ô ở nửa dưới lịch; kẹp mép trái.
  function anchorTo(el: HTMLElement) {
    const g = gridRef.current;
    if (!g) return;
    const POP = 280;
    const gr = g.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    const x = r.left - gr.left;
    const y = r.top - gr.top;
    const left = Math.max(4, Math.min(x, g.clientWidth - POP - 4));
    const above = y > g.clientHeight * 0.55;
    const top = above ? y - 6 : y + r.height + 6;
    setPop({ left, top, above });
  }

  function openNew(dayStr: string, el: HTMLElement) {
    setSel(null);
    setFormDay(dayStr);
    setFNote(""); setFTime("09:00"); setFFreq("none"); setFEvery(1); setFUntil("");
    anchorTo(el);
  }
  function openPill(o: CareOccurrence, dayStr: string, el: HTMLElement) {
    setFormDay(null);
    setReDate(dayStr);
    setSel(o);
    anchorTo(el);
  }

  async function create() {
    if (!token || busy || !fNote.trim() || !formDay) return;
    setBusy(true);
    try {
      await api.customers.addCareTask(token, customerId, {
        note: fNote.trim(),
        due_date: new Date(`${formDay}T${fTime || "09:00"}:00`).toISOString(),
        repeat_freq: fFreq,
        repeat_interval: Math.max(1, fEvery),
        repeat_until: fFreq !== "none" && fUntil ? new Date(`${fUntil}T23:59:59`).toISOString() : null,
      });
      closePop();
      load();
      onChange?.();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Tạo hẹn không thành công.");
    } finally { setBusy(false); }
  }

  async function act(
    o: CareOccurrence,
    action: "complete" | "cancel" | "reschedule",
    extra?: { new_due?: string },
  ) {
    if (!token || busy) return;
    const headId = o.series_id ?? o.task_id;
    if (headId == null) return;
    setBusy(true);
    try {
      const r = await api.customers.actOnOccurrence(token, customerId, headId, from, to, {
        action,
        occurrence_date: o.due_date,
        new_due: extra?.new_due ?? null,
      });
      setOcc(r.items);
      closePop(); setReDate("");
      onChange?.();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Thao tác không thành công.");
    } finally { setBusy(false); }
  }

  // Mở lại 1 việc đã xong/đã huỷ (dòng cụ thể có task_id) → về "đang mở".
  async function reopen(taskId: number) {
    if (!token || busy) return;
    setBusy(true);
    try {
      await api.customers.setCareTaskStatus(token, customerId, taskId, { status: "open" });
      closePop();
      load();
      onChange?.();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Mở lại không thành công.");
    } finally { setBusy(false); }
  }

  // Tick tròn: đang mở → hoàn thành (gạch); đã xong → mở lại.
  function toggleDone(o: CareOccurrence, e: React.MouseEvent) {
    e.stopPropagation();
    if (busy) return;
    if (o.status === "open") act(o, "complete");
    else if (o.status === "done" && o.task_id != null) reopen(o.task_id);
  }

  // Thả thẻ hẹn xuống 1 ô ngày → dời hẹn sang ngày đó (giữ nguyên giờ).
  function onDropDay(dayStr: string) {
    const o = dragRef.current;
    dragRef.current = null;
    setDropDay(null);
    if (!o || o.due_date.slice(0, 10) === dayStr) return;
    const time = o.due_date.slice(11, 16) || "09:00";
    act(o, "reschedule", { new_due: new Date(`${dayStr}T${time}:00`).toISOString() });
  }

  return (
    <div className="cc">
      <div className="cc__bar">
        <div className="cc__nav">
          <button className="cc__icon-btn" onClick={() => move(-1)} aria-label="Tháng trước"><ChevronLeft size={16} /></button>
          <span className="cc__month">Tháng {ym.m + 1} · {ym.y}</span>
          <button className="cc__icon-btn" onClick={() => move(1)} aria-label="Tháng sau"><ChevronRight size={16} /></button>
        </div>
        {canUpdate && <span className="cc__hint">Bấm 1 ô ngày để đặt hẹn<span className="cc__hint-tick"> · tick tròn khi làm xong</span></span>}
      </div>

      {err && <div className="banner banner--error">{err}</div>}

      <div className="cc__grid" ref={gridRef}>
        {WD.map((w) => <div key={w} className="cc__wd">{w}</div>)}
        {cells.map((d, i) => {
          if (!d) return <div key={i} className="cc__cell cc__cell--blank" />;
          const k = ymd(d);
          const list = byDay[k] ?? [];
          const isToday = k === todayStr;
          return (
            <div
              key={i}
              data-day={k}
              className={`cc__cell${isToday ? " cc__cell--today" : ""}${dropDay === k ? " cc__cell--drop" : ""}`}
              onClick={(e) => canUpdate && openNew(k, e.currentTarget)}
              onDragOver={(e) => { if (dragRef.current) { e.preventDefault(); setDropDay(k); } }}
              onDragLeave={() => setDropDay((p) => (p === k ? null : p))}
              onDrop={(e) => { e.preventDefault(); onDropDay(k); }}
            >
              <div className="cc__dn">{d.getDate()}</div>
              {list.map((o, j) => {
                const drag = canUpdate && o.status === "open";
                const tickable = canUpdate && o.status !== "cancelled";
                return (
                  <span
                    key={j}
                    className={pillClass(o)}
                    title={o.note}
                    draggable={drag}
                    style={drag ? { cursor: "grab" } : undefined}
                    onDragStart={(e) => { if (drag) { dragRef.current = o; e.dataTransfer.effectAllowed = "move"; } }}
                    onDragEnd={() => { dragRef.current = null; setDropDay(null); }}
                    onClick={(e) => { e.stopPropagation(); openPill(o, k, e.currentTarget); }}
                  >
                    {tickable ? (
                      <button
                        type="button"
                        className="cc__tick"
                        aria-label={o.status === "done" ? "Bỏ đánh dấu xong" : "Đánh dấu đã xong"}
                        onMouseDown={(e) => e.stopPropagation()}
                        onClick={(e) => toggleDone(o, e)}
                      >
                        {o.status === "done" ? <Check size={11} /> : null}
                      </button>
                    ) : null}
                    {recurring(o) && <Repeat size={10} className="cc__pill-rep" />}
                    <span className="cc__pill-note">{o.note}</span>
                  </span>
                );
              })}
            </div>
          );
        })}

        {(formDay || sel) && pop && (
          <div
            ref={popRef}
            className="cc__pop"
            style={{ left: pop.left, top: pop.top, transform: pop.above ? "translateY(-100%)" : undefined }}
          >
            {formDay && canUpdate ? (
              <>
                <div className="cc__panel-head">
                  <div className="cc__panel-title">Đặt hẹn</div>
                  <button className="cc__icon-btn" onClick={closePop} aria-label="Đóng"><X size={15} /></button>
                </div>
                <div className="cc__panel-sub">{formDay}</div>
                <input
                  className="cc__input cc__input--full"
                  autoFocus
                  placeholder="Việc cần làm (vd: gọi hỏi tiến độ đơn)"
                  value={fNote}
                  onChange={(e) => setFNote(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") create(); }}
                />
                <div className="cc__row">
                  <div className="cc__field">
                    <span className="cc__label">Giờ</span>
                    <input type="time" className="cc__input" value={fTime} onChange={(e) => setFTime(e.target.value)} />
                  </div>
                  <div className="cc__field">
                    <span className="cc__label">Lặp</span>
                    <select className="cc__select" value={fFreq} onChange={(e) => setFFreq(e.target.value)}>
                      <option value="none">Không lặp</option>
                      <option value="day">Mỗi ngày</option>
                      <option value="week">Mỗi tuần</option>
                      <option value="month">Mỗi tháng</option>
                    </select>
                  </div>
                </div>
                {fFreq !== "none" && (
                  <div className="cc__row">
                    <div className="cc__field">
                      <span className="cc__label">Mỗi</span>
                      <input type="number" min={1} className="cc__input" style={{ width: 64 }} value={fEvery} onChange={(e) => setFEvery(Number(e.target.value))} />
                    </div>
                    <div className="cc__field">
                      <span className="cc__label">Đến ngày</span>
                      <input type="date" className="cc__input" value={fUntil} onChange={(e) => setFUntil(e.target.value)} />
                    </div>
                  </div>
                )}
                <div className="cc__actions">
                  <button className="btn btn--primary" disabled={busy || !fNote.trim()} onClick={create}>
                    {busy ? "Đang lưu…" : "Lưu hẹn"}
                  </button>
                </div>
              </>
            ) : sel ? (
              <>
                <div className="cc__panel-head">
                  <div>
                    <div className="cc__panel-title">{sel.note}</div>
                    <div className="cc__panel-sub">
                      {sel.due_date.slice(0, 10)} ·{" "}
                      {sel.status === "done"
                        ? "đã xong"
                        : sel.status === "cancelled"
                          ? "đã huỷ"
                          : sel.remind_level >= 1
                            ? `đến hạn (nhắc lần ${sel.remind_level})`
                            : "chưa tới hạn"}
                      {sel.assignee_name ? ` · ${sel.assignee_name}` : ""}
                    </div>
                  </div>
                  <button className="cc__icon-btn" onClick={closePop} aria-label="Đóng"><X size={15} /></button>
                </div>
                {recurring(sel) && (
                  <span className="cc__chip"><Repeat size={11} /> Lặp mỗi {freqLabel(sel.repeat_freq)}</span>
                )}
                {canUpdate && sel.status === "open" && (
                  <>
                    <div className="cc__actions">
                      <button className="btn btn--primary" disabled={busy} onClick={() => act(sel, "complete")}>
                        <Check size={14} /> Đã xong
                      </button>
                      <input type="date" className="cc__input" value={reDate} onChange={(e) => setReDate(e.target.value)} />
                      <button
                        className="btn btn--ghost" disabled={busy || !reDate}
                        onClick={() => act(sel, "reschedule", { new_due: new Date(`${reDate}T09:00:00`).toISOString() })}
                      >
                        <RotateCcw size={14} /> Dời
                      </button>
                      <button className="btn btn--ghost" disabled={busy} onClick={() => act(sel, "cancel")}>
                        <X size={14} /> Huỷ lần này
                      </button>
                    </div>
                    <div className="cc__pop-tip">Mẹo: tick tròn trên thẻ để xong nhanh, hoặc kéo thẻ sang ô khác để dời.</div>
                  </>
                )}
                {canUpdate && sel.status !== "open" && sel.task_id != null && (
                  <div className="cc__actions">
                    <button className="btn btn--ghost" disabled={busy} onClick={() => reopen(sel.task_id!)}>
                      <RotateCcw size={14} /> Mở lại
                    </button>
                  </div>
                )}
              </>
            ) : null}
          </div>
        )}
      </div>

      <div className="cc__legend">
        <span className="cc__lg"><span className="cc__sw" style={{ background: "var(--rule-soft)" }} />chưa tới</span>
        <span className="cc__lg"><span className="cc__sw" style={{ background: "var(--amber-soft)" }} />đến hạn</span>
        <span className="cc__lg"><span className="cc__sw" style={{ background: "var(--rust-soft)" }} />quá hạn</span>
        <span className="cc__lg"><Check size={13} /> xong<span className="cc__lg-strike"> (gạch ngang)</span></span>
        <span className="cc__lg"><Repeat size={13} /> hẹn lặp</span>
      </div>
    </div>
  );
}
