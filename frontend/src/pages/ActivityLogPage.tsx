import { useEffect, useMemo, useState } from "react";
import { ApiError, api, type AuditRow } from "../api/client";
import { useAuth } from "../auth/useAuth";
import "./activity.css";

const ACTION_LABELS: Record<string, string> = {
  create_role: "Tạo vai trò",
  rename_role: "Đổi tên vai trò",
  delete_role: "Xóa vai trò",
  update_role_permissions: "Sửa quyền vai trò",
  create_department: "Tạo phòng ban",
  update_department: "Cập nhật phòng ban",
  delete_department: "Xóa phòng ban",
  create_user: "Tạo người dùng",
  assign_role: "Gán vai trò",
  lock_user: "Khóa tài khoản",
  unlock_user: "Mở khóa tài khoản",
};

function actionLabel(code: string): string {
  return ACTION_LABELS[code] ?? code;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("vi-VN");
}

export function ActivityLogPage() {
  const { token } = useAuth();
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.rbac
      .activityLog(token)
      .then((data) => !cancelled && setRows(data))
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được nhật ký hoạt động.");
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [token]);

  const actions = useMemo(() => Array.from(new Set(rows.map((r) => r.action))), [rows]);
  const filtered = filter === "all" ? rows : rows.filter((r) => r.action === filter);

  if (forbidden) {
    return (
      <main className="activity">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Nhật ký hoạt động.
        </div>
      </main>
    );
  }

  return (
    <main className="activity">
      <header className="activity__head">
        <div>
          <p className="eyebrow">Quản trị</p>
          <h1 className="activity__title">Nhật ký hoạt động</h1>
          <p className="activity__sub">Lịch sử các thay đổi phân quyền (chỉ xem).</p>
        </div>
        <label className="activity__filter">
          <span className="activity__filter-label">Lọc theo hành động</span>
          <select className="input input--sm" value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">Tất cả</option>
            {actions.map((a) => (
              <option key={a} value={a}>
                {actionLabel(a)}
              </option>
            ))}
          </select>
        </label>
      </header>

      <section className="card activity__card">
        {loading ? (
          <p className="activity__status" role="status">
            Đang tải…
          </p>
        ) : error ? (
          <div className="banner banner--error" role="alert">
            <span>{error}</span>
            <button type="button" className="btn btn--ghost" onClick={() => location.reload()}>
              Thử lại
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <p className="activity__status">Chưa có hoạt động.</p>
        ) : (
          <table className="activity__table">
            <thead>
              <tr>
                <th>Thời gian</th>
                <th>Người thực hiện</th>
                <th>Hành động</th>
                <th>Đối tượng</th>
                <th>Chi tiết</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.id}>
                  <td className="activity__time">{formatTime(r.created_at)}</td>
                  <td>{r.actor_name ?? <span className="activity__muted">Hệ thống</span>}</td>
                  <td>{actionLabel(r.action)}</td>
                  <td className="activity__mono">{r.target}</td>
                  <td>{r.detail || <span className="activity__muted">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
