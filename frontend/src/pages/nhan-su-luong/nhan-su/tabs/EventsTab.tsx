// Tab Quá trình công tác của hồ sơ nhân sự (tách từ pages/NhanSuPage.tsx).
import { useCallback, useEffect, useState } from "react";
import { api, type EmployeeEvent, type EmployeeMeta } from "../../../../api/client";
import { EmptyState } from "../../../../components/EmptyState";
import { Timeline, type TimelineEntry } from "../../../../components/Timeline";
import { fmtDate } from "../../../../utils/format";
import { EVENT_LABEL, STATUS_LABEL } from "../shared/constants";
import { errMsg } from "../shared/helpers";

export function EventsTab({
  token,
  employeeId,
  meta,
}: {
  token: string;
  employeeId: number;
  meta: EmployeeMeta | null;
}) {
  const [events, setEvents] = useState<EmployeeEvent[] | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const load = useCallback(() => {
    setLoi(null);
    api.employees
      .events(token, employeeId)
      .then((r) => setEvents(r.items))
      .catch((e) => {
        setEvents([]);
        setLoi(errMsg(e));
      });
  }, [token, employeeId]);
  useEffect(() => {
    load();
  }, [load]);
  if (loi)
    return <EmptyState trangThai="loi" loi={loi} onThuLai={load} />;
  if (!events) return <EmptyState trangThai="dang-tai" />;

  // Dịch giá trị thô (mã trạng thái / id phòng / bậc) sang chữ dễ hiểu cho nhân viên.
  const humanize = (field: string | null, v: string | null): string | null => {
    if (!v) return null;
    if (field === "status") return STATUS_LABEL[v] ?? v;
    if (field === "department") {
      const d = meta?.departments.find((x) => String(x.id) === v);
      return d ? d.name : `phòng #${v}`;
    }
    return v; // bậc tay nghề ("Thợ vững"), chức danh…
  };

  const items: TimelineEntry[] = events.map((ev) => {
    const f = humanize(ev.field, ev.from_value);
    const t = humanize(ev.field, ev.to_value);
    // "Vào làm" tự đủ nghĩa → không kèm "— → Thử việc". Còn lại: "A → B" hoặc chỉ "B".
    let change = "";
    if (ev.event_type !== "hired") {
      if (f && t) change = `${f} → ${t}`;
      else if (t) change = t;
    }
    const detailBits = [
      fmtDate(ev.effective_date),
      ev.note || null,
      ev.actor_name ? `Người thực hiện: ${ev.actor_name}` : null,
    ].filter(Boolean);
    const tone: TimelineEntry["tone"] | undefined =
      ev.event_type === "hired"
        ? "rust"
        : ["confirmed", "promoted", "leave_end", "reinstated"].includes(
              ev.event_type,
            )
          ? "moss"
          : ev.event_type === "transferred"
            ? "steel"
            : ["resigned", "suspended", "leave_start"].includes(ev.event_type)
              ? "signal"
              : undefined;
    return {
      title: change
        ? `${EVENT_LABEL[ev.event_type] ?? ev.event_type}: ${change}`
        : (EVENT_LABEL[ev.event_type] ?? ev.event_type),
      meta: detailBits.join(" · "),
      accent: tone === "moss" || tone === "rust",
      tone,
    };
  });
  return <Timeline items={items} emptyText="Chưa có mốc quá trình công tác." />;
}
