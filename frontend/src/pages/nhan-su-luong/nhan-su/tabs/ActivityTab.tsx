// Tab Nhật ký của hồ sơ nhân sự (tách từ pages/NhanSuPage.tsx).
import { useCallback, useEffect, useState } from "react";
import { api } from "../../../../api/client";
import { EmptyState } from "../../../../components/EmptyState";
import { Timeline, type TimelineEntry } from "../../../../components/Timeline";
import { fmtDateTime } from "../../../../utils/format";
import { errMsg } from "../shared/helpers";

export function ActivityTab({
  token,
  employeeId,
  lanNap,
}: {
  token: string;
  employeeId: number;
  /** Đổi mỗi lần khay hồ sơ nạp lại sau thao tác — tải lại nhật ký để dòng mới hiện ngay. */
  lanNap: number;
}) {
  const [items, setItems] = useState<
    | {
        action: string;
        detail: string;
        actor_name: string | null;
        created_at: string;
      }[]
    | null
  >(null);
  const [loi, setLoi] = useState<string | null>(null);
  const load = useCallback(() => {
    setLoi(null);
    api.employees
      .activity(token, employeeId)
      .then((r) => setItems(r.items))
      .catch((e) => {
        setItems([]);
        setLoi(errMsg(e));
      });
  }, [token, employeeId]);
  useEffect(() => {
    load();
  }, [load, lanNap]);
  if (loi) return <EmptyState trangThai="loi" loi={loi} onThuLai={load} />;
  if (!items) return <EmptyState trangThai="dang-tai" />;
  const tl: TimelineEntry[] = items.map((a) => ({
    title: a.detail || a.action,
    meta: `${fmtDateTime(a.created_at)}${a.actor_name ? ` · ${a.actor_name}` : ""}`,
  }));
  return <Timeline items={tl} emptyText="Chưa có hoạt động." />;
}
