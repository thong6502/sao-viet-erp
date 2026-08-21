import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Calendar,
  ShieldCheck,
  UserCheck,
  Clock,
  Search,
  Filter,
  Layers,
  RefreshCw,
  SlidersHorizontal,
  List,
  Building,
  UserX,
  User,
  ArrowRight,
  Lock,
  Unlock,
  Tag,
  Copy,
  Check,
  RotateCcw,
  ChevronLeft,
  ChevronRight,
  Eye,
  X,
  FileText,
  Download,
  CheckCircle2,
} from "lucide-react";
import { ApiError, api, type AuditRow } from "../api/client";
import { useAuth } from "../auth/useAuth";
import "./activity.css";

type ActionCategory = "lsx" | "rbac" | "user" | "dept" | "other";

interface ActionMeta {
  label: string;
  category: ActionCategory;
  badgeClass: string;
  icon: typeof Activity;
}

const ACTION_REGISTRY: Record<string, ActionMeta> = {
  // Lệnh sản xuất & Xếp lịch
  xep_lich_dua_vao: {
    label: "Đưa vào xếp lịch",
    category: "lsx",
    badgeClass: "badge--purple",
    icon: Calendar,
  },
  xep_lich_mo_khoa: {
    label: "Mở khóa lịch",
    category: "lsx",
    badgeClass: "badge--indigo",
    icon: Unlock,
  },
  xep_lich_khoa: {
    label: "Khóa lịch",
    category: "lsx",
    badgeClass: "badge--indigo",
    icon: Lock,
  },
  lsx_trang_thai: {
    label: "Đổi trạng thái LSX",
    category: "lsx",
    badgeClass: "badge--blue",
    icon: Activity,
  },
  update_lsx: {
    label: "Cập nhật LSX",
    category: "lsx",
    badgeClass: "badge--purple",
    icon: Layers,
  },

  // Vai trò & Phân quyền
  create_role: {
    label: "Tạo vai trò",
    category: "rbac",
    badgeClass: "badge--emerald",
    icon: ShieldCheck,
  },
  rename_role: {
    label: "Đổi tên vai trò",
    category: "rbac",
    badgeClass: "badge--emerald",
    icon: ShieldCheck,
  },
  delete_role: {
    label: "Xóa vai trò",
    category: "rbac",
    badgeClass: "badge--rose",
    icon: ShieldCheck,
  },
  update_role_permissions: {
    label: "Sửa quyền vai trò",
    category: "rbac",
    badgeClass: "badge--emerald",
    icon: ShieldCheck,
  },

  // Phòng ban
  create_department: {
    label: "Tạo phòng ban",
    category: "dept",
    badgeClass: "badge--cyan",
    icon: Building,
  },
  update_department: {
    label: "Cập nhật phòng ban",
    category: "dept",
    badgeClass: "badge--cyan",
    icon: Building,
  },
  delete_department: {
    label: "Xóa phòng ban",
    category: "dept",
    badgeClass: "badge--rose",
    icon: Building,
  },

  // Người dùng
  create_user: {
    label: "Tạo người dùng",
    category: "user",
    badgeClass: "badge--amber",
    icon: UserCheck,
  },
  assign_role: {
    label: "Gán vai trò",
    category: "user",
    badgeClass: "badge--amber",
    icon: UserCheck,
  },
  lock_user: {
    label: "Khóa tài khoản",
    category: "user",
    badgeClass: "badge--rose",
    icon: UserX,
  },
  unlock_user: {
    label: "Mở khóa tài khoản",
    category: "user",
    badgeClass: "badge--emerald",
    icon: UserCheck,
  },
};

function getActionMeta(actionCode: string): ActionMeta {
  if (ACTION_REGISTRY[actionCode]) {
    return ACTION_REGISTRY[actionCode];
  }
  const formattedLabel = actionCode
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");

  return {
    label: formattedLabel,
    category: "other",
    badgeClass: "badge--slate",
    icon: Tag,
  };
}

function formatExactTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatRelativeTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;

  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHours = Math.floor(diffMin / 60);

  if (diffSec < 45) return "Vừa xong";
  if (diffMin < 60) return `${diffMin} phút trước`;
  if (diffHours < 24 && now.getDate() === d.getDate()) {
    return `Hôm nay ${d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}`;
  }

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (yesterday.getDate() === d.getDate() && yesterday.getMonth() === d.getMonth()) {
    return `Hôm qua ${d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}`;
  }

  return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
}

function getDateGroupLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Khác";

  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterdayStart = todayStart - 86400000;
  const weekStart = todayStart - 6 * 86400000;

  const time = d.getTime();
  if (time >= todayStart) return "Hôm nay";
  if (time >= yesterdayStart) return "Hôm qua";
  if (time >= weekStart) return "7 ngày qua";

  return d.toLocaleDateString("vi-VN", { month: "long", year: "numeric" });
}

function getUserInitials(name: string | null): string {
  if (!name || name.trim() === "") return "HT";
  const parts = name.trim().split(" ");
  if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Detail Component */
function FormattedDetail({ detail }: { detail: string | null }) {
  const [copiedText, setCopiedText] = useState<string | null>(null);

  if (!detail) return <span className="act-muted">—</span>;

  const handleCopy = (text: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopiedText(text);
    setTimeout(() => setCopiedText(null), 1800);
  };

  // Status transitions
  if (detail.includes("→")) {
    const parts = detail.split("→");
    const targetStatus = parts[1].trim();
    return (
      <span className="act-detail__highlighted">
        <span className="act-detail__text">{parts[0].trim()}</span>
        <ArrowRight size={12} className="act-detail__arrow" />
        <span className="act-detail__status-tag">{targetStatus}</span>
      </span>
    );
  }

  // Highlight LSX codes (e.g. LSX26-0007)
  const lsxMatch = detail.match(/LSX\d+[-\w]*/i);
  if (lsxMatch) {
    const code = lsxMatch[0];
    const parts = detail.split(code);
    return (
      <span className="act-detail__inline-flex">
        {parts[0]}
        <span
          className="act-detail__code-tag"
          onClick={(e) => handleCopy(code, e)}
          title="Click để copy mã LSX"
        >
          {code}
          {copiedText === code ? (
            <Check size={10} className="act-copy-icon act-copy-icon--success" />
          ) : (
            <Copy size={10} className="act-copy-icon" />
          )}
        </span>
        {parts.slice(1).join(code)}
      </span>
    );
  }

  return <span className="act-detail__text">{detail}</span>;
}

export function ActivityLogPage() {
  const { token } = useAuth();
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  // Filters & Controls
  const [searchQuery, setSearchQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<"all" | ActionCategory>("all");
  const [actionFilter, setActionFilter] = useState("all");
  const [actorFilter, setActorFilter] = useState("all");
  const [timeRange, setTimeRange] = useState<"all" | "24h" | "7d" | "30d">("all");
  const [viewMode, setViewMode] = useState<"timeline" | "table">("timeline");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  // Modal / Drawer Inspector State
  const [selectedRow, setSelectedRow] = useState<AuditRow | null>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 2200);
  };

  const fetchLogs = () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.rbac
      .activityLog(token)
      .then((data) => setRows(data))
      .catch((err) => {
        if (err instanceof ApiError && err.isForbidden) setForbidden(true);
        else setError("Không tải được nhật ký hoạt động.");
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchLogs();
  }, [token]);

  // Options
  const availableActions = useMemo(() => Array.from(new Set(rows.map((r) => r.action))), [rows]);
  const availableActors = useMemo(
    () => Array.from(new Set(rows.map((r) => r.actor_name || "Hệ thống"))),
    [rows]
  );

  // Category counts
  const categoryCounts = useMemo(() => {
    const counts = { all: rows.length, lsx: 0, rbac: 0, user: 0, dept: 0, other: 0 };
    rows.forEach((r) => {
      const meta = getActionMeta(r.action);
      if (counts[meta.category] !== undefined) {
        counts[meta.category]++;
      }
    });
    return counts;
  }, [rows]);

  // Filtered rows
  const filteredRows = useMemo(() => {
    const now = Date.now();
    return rows.filter((r) => {
      const meta = getActionMeta(r.action);

      if (categoryFilter !== "all" && meta.category !== categoryFilter) return false;
      if (actionFilter !== "all" && r.action !== actionFilter) return false;

      const actorName = r.actor_name || "Hệ thống";
      if (actorFilter !== "all" && actorName !== actorFilter) return false;

      // Time range filter
      if (timeRange !== "all") {
        const itemTime = new Date(r.created_at).getTime();
        if (Number.isNaN(itemTime)) return true;
        const diffHours = (now - itemTime) / (1000 * 60 * 60);
        if (timeRange === "24h" && diffHours > 24) return false;
        if (timeRange === "7d" && diffHours > 24 * 7) return false;
        if (timeRange === "30d" && diffHours > 24 * 30) return false;
      }

      // Search Query Filter
      if (searchQuery.trim() !== "") {
        const q = searchQuery.toLowerCase().trim();
        const matchAction = meta.label.toLowerCase().includes(q) || r.action.toLowerCase().includes(q);
        const matchActor = actorName.toLowerCase().includes(q);
        const matchTarget = (r.target || "").toLowerCase().includes(q);
        const matchDetail = (r.detail || "").toLowerCase().includes(q);
        if (!matchAction && !matchActor && !matchTarget && !matchDetail) return false;
      }

      return true;
    });
  }, [rows, categoryFilter, actionFilter, actorFilter, timeRange, searchQuery]);

  useEffect(() => {
    setPage(1);
  }, [categoryFilter, actionFilter, actorFilter, timeRange, searchQuery]);

  // Pagination
  const totalPages = Math.ceil(filteredRows.length / pageSize) || 1;
  const paginatedRows = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredRows.slice(start, start + pageSize);
  }, [filteredRows, page, pageSize]);

  // Grouped Timeline Rows
  const groupedTimeline = useMemo(() => {
    const groups: { label: string; items: AuditRow[] }[] = [];
    let currentLabel = "";
    let currentItems: AuditRow[] = [];

    paginatedRows.forEach((r) => {
      const groupLabel = getDateGroupLabel(r.created_at);
      if (groupLabel !== currentLabel) {
        if (currentItems.length > 0) {
          groups.push({ label: currentLabel, items: currentItems });
        }
        currentLabel = groupLabel;
        currentItems = [r];
      } else {
        currentItems.push(r);
      }
    });

    if (currentItems.length > 0) {
      groups.push({ label: currentLabel, items: currentItems });
    }

    return groups;
  }, [paginatedRows]);

  const exportCSV = () => {
    if (filteredRows.length === 0) return;
    const headers = ["ID", "Thoi gian", "Nguoi thuc hien", "Hanh dong", "Doi tuong", "Chi tiet"];
    const rowsCsv = filteredRows.map((r) => {
      const timeStr = formatExactTime(r.created_at);
      const actorStr = r.actor_name || "Hệ thống";
      const actionStr = getActionMeta(r.action).label;
      const targetStr = r.target || "";
      const detailStr = (r.detail || "").split('"').join('""');
      return `${r.id},"${timeStr}","${actorStr}","${actionStr}","${targetStr}","${detailStr}"`;
    });
    const csvContent = [headers.join(","), ...rowsCsv].join("\n");

    const blob = new Blob(["\ufeff" + csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `nhat-ky-hoat-dong-${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showToast("Đã xuất CSV nhật ký hoạt động!");
  };

  if (forbidden) {
    return (
      <main className="act-page">
        <div className="banner banner--error" role="alert">
          Bạn không có quyền truy cập Nhật ký hoạt động.
        </div>
      </main>
    );
  }

  const selectedMeta = selectedRow ? getActionMeta(selectedRow.action) : null;
  const SelectedIcon = selectedMeta ? selectedMeta.icon : null;

  return (
    <main className="act-page">
      {/* TOAST NOTIFICATION */}
      {toastMsg && (
        <div className="act-toast" role="status">
          <CheckCircle2 size={15} />
          <span>{toastMsg}</span>
        </div>
      )}

      {/* HEADER SECTION */}
      <header className="act-header">
        <div className="act-header__left">
          <div className="act-header__badge-row">
            <span className="act-eyebrow">QUẢN LÝ HỆ THỐNG</span>
            <span className="act-live-pulse" title="Hệ thống luôn ghi nhận tức thì">
              <span className="act-pulse-dot" />
              Đồng bộ Live
            </span>
          </div>
          <h1 className="act-title">Nhật ký hoạt động</h1>
          <p className="act-sub">
            Lịch sử truy vết audit trail phân quyền, lệnh sản xuất &amp; thao tác hệ thống theo thời gian thực.
          </p>
        </div>

        <div className="act-header__right">
          <button
            type="button"
            className="act-btn-glass"
            onClick={exportCSV}
            disabled={filteredRows.length === 0}
            title="Xuất file CSV báo cáo audit log"
          >
            <Download size={14} />
            <span>Xuất CSV</span>
          </button>

          <button
            type="button"
            className="act-btn-compact"
            onClick={fetchLogs}
            disabled={loading}
            title="Tải lại nhật ký hoạt động"
          >
            <RefreshCw size={13} className={loading ? "act-spin" : ""} />
            <span>{loading ? "Đang nạp…" : "Làm mới"}</span>
          </button>
        </div>
      </header>

      {/* TOOLBAR & CATEGORY FILTER BAR */}
      <section className="act-toolbar">
        <div className="act-toolbar__row">
          {/* Search Box */}
          <div className="act-search-box">
            <Search size={14} className="act-search-icon" />
            <input
              type="text"
              className="act-search-input"
              placeholder="Tìm người thao tác, mã LSX, đối tượng, nội dung..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button
                type="button"
                className="act-search-clear"
                onClick={() => setSearchQuery("")}
                title="Xóa tìm kiếm"
              >
                <X size={12} />
              </button>
            )}
          </div>

          {/* Time Range Preset Dropdown */}
          <div className="act-select-group">
            <Clock size={13} className="act-select-icon" />
            <select
              className="act-select-input"
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value as any)}
            >
              <option value="all">Tất cả thời gian</option>
              <option value="24h">24 giờ qua</option>
              <option value="7d">7 ngày qua</option>
              <option value="30d">30 ngày qua</option>
            </select>
          </div>

          {/* Action Select Filter */}
          <div className="act-select-group">
            <SlidersHorizontal size={13} className="act-select-icon" />
            <select
              className="act-select-input"
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
            >
              <option value="all">Tất cả hành động</option>
              {availableActions.map((act) => (
                <option key={act} value={act}>
                  {getActionMeta(act).label}
                </option>
              ))}
            </select>
          </div>

          {/* Actor Select Filter */}
          <div className="act-select-group">
            <User size={13} className="act-select-icon" />
            <select
              className="act-select-input"
              value={actorFilter}
              onChange={(e) => setActorFilter(e.target.value)}
            >
              <option value="all">Tất cả người thao tác</option>
              {availableActors.map((actor) => (
                <option key={actor} value={actor}>
                  {actor}
                </option>
              ))}
            </select>
          </div>

          {/* View Mode Switcher */}
          <div className="act-view-toggle">
            <button
              type="button"
              className={`act-view-btn ${viewMode === "timeline" ? "act-view-btn--active" : ""}`}
              onClick={() => setViewMode("timeline")}
            >
              <Clock size={13} />
              <span>Timeline</span>
            </button>
            <button
              type="button"
              className={`act-view-btn ${viewMode === "table" ? "act-view-btn--active" : ""}`}
              onClick={() => setViewMode("table")}
            >
              <List size={13} />
              <span>Table</span>
            </button>
          </div>
        </div>

        {/* Category Pills Row with Counts */}
        <div className="act-category-row">
          <button
            type="button"
            className={`act-pill ${categoryFilter === "all" ? "act-pill--active" : ""}`}
            onClick={() => setCategoryFilter("all")}
          >
            <span>Tất cả</span>
            <span className="act-pill-count">{categoryCounts.all}</span>
          </button>

          <button
            type="button"
            className={`act-pill ${categoryFilter === "lsx" ? "act-pill--active act-pill--purple" : ""}`}
            onClick={() => setCategoryFilter("lsx")}
          >
            <Layers size={12} />
            <span>Sản xuất &amp; Xếp lịch</span>
            <span className="act-pill-count">{categoryCounts.lsx}</span>
          </button>

          <button
            type="button"
            className={`act-pill ${categoryFilter === "rbac" ? "act-pill--active act-pill--emerald" : ""}`}
            onClick={() => setCategoryFilter("rbac")}
          >
            <ShieldCheck size={12} />
            <span>Phân quyền</span>
            <span className="act-pill-count">{categoryCounts.rbac}</span>
          </button>

          <button
            type="button"
            className={`act-pill ${categoryFilter === "user" ? "act-pill--active act-pill--amber" : ""}`}
            onClick={() => setCategoryFilter("user")}
          >
            <UserCheck size={12} />
            <span>Người dùng</span>
            <span className="act-pill-count">{categoryCounts.user}</span>
          </button>

          <button
            type="button"
            className={`act-pill ${categoryFilter === "dept" ? "act-pill--active act-pill--cyan" : ""}`}
            onClick={() => setCategoryFilter("dept")}
          >
            <Building size={12} />
            <span>Phòng ban</span>
            <span className="act-pill-count">{categoryCounts.dept}</span>
          </button>
        </div>
      </section>

      {/* MAIN CONTENT CARD */}
      <section className="act-card">
        {loading ? (
          /* Sleek Skeleton Loading State */
          <div className="act-skeleton-container">
            {[1, 2, 3, 4, 5].map((i) => (
              <div className="act-skeleton-row" key={i}>
                <div className="act-skeleton-avatar" />
                <div className="act-skeleton-body">
                  <div className="act-skeleton-line act-skeleton-line--short" />
                  <div className="act-skeleton-line act-skeleton-line--long" />
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="banner banner--error" role="alert">
            <span>{error}</span>
            <button type="button" className="btn btn--ghost" onClick={fetchLogs}>
              Thử lại
            </button>
          </div>
        ) : filteredRows.length === 0 ? (
          <div className="act-empty">
            <Filter size={32} className="act-empty-icon" />
            <p className="act-empty-title">Không tìm thấy nhật ký phù hợp</p>
            <p className="act-empty-desc">Thử điều chỉnh bộ lọc hoặc từ khóa tìm kiếm của bạn.</p>
            {(searchQuery ||
              categoryFilter !== "all" ||
              actionFilter !== "all" ||
              actorFilter !== "all" ||
              timeRange !== "all") && (
              <button
                type="button"
                className="act-btn-ghost-sm"
                onClick={() => {
                  setSearchQuery("");
                  setCategoryFilter("all");
                  setActionFilter("all");
                  setActorFilter("all");
                  setTimeRange("all");
                }}
              >
                <RotateCcw size={12} />
                Đặt lại bộ lọc
              </button>
            )}
          </div>
        ) : viewMode === "timeline" ? (
          /* CONNECTED VISUAL TIMELINE WITH DATE GROUPING */
          <div className="act-timeline-container">
            {groupedTimeline.map((group) => (
              <div className="act-tl-group" key={group.label}>
                <div className="act-tl-group-header">
                  <Calendar size={13} />
                  <span>{group.label}</span>
                  <span className="act-tl-group-count">{group.items.length} bản ghi</span>
                </div>

                <div className="act-timeline">
                  {group.items.map((r) => {
                    const meta = getActionMeta(r.action);
                    const IconComp = meta.icon;
                    const actorName = r.actor_name || "Hệ thống";

                    return (
                      <div
                        className="act-tl-row"
                        key={r.id}
                        onClick={() => setSelectedRow(r)}
                        title="Click để xem chi tiết bản ghi nhật ký này"
                      >
                        <div className="act-tl-avatar-container">
                          <div className={`act-tl-node ${meta.badgeClass}`}>
                            <IconComp size={12} />
                          </div>
                        </div>

                        <div className="act-tl-content">
                          <div className="act-tl-head">
                            <span className="act-avatar-xs">{getUserInitials(r.actor_name)}</span>
                            <span className="act-tl-actor">{actorName}</span>

                            <span className={`act-badge ${meta.badgeClass}`}>
                              <IconComp size={11} />
                              {meta.label}
                            </span>

                            {r.target && (
                              <span className="act-target-pill">
                                <Tag size={11} />
                                {r.target}
                              </span>
                            )}

                            <span className="act-tl-time" title={formatExactTime(r.created_at)}>
                              <Clock size={11} />
                              {formatRelativeTime(r.created_at)}
                            </span>
                          </div>

                          <div className="act-tl-body">
                            <FormattedDetail detail={r.detail} />
                          </div>
                        </div>

                        <div className="act-tl-meta">
                          <span className="act-tl-exact">{formatExactTime(r.created_at)}</span>
                          <span className="act-tl-id">#{r.id}</span>
                          <button
                            type="button"
                            className="act-btn-inspect"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedRow(r);
                            }}
                            title="Xem chi tiết đầy đủ"
                          >
                            <Eye size={12} />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        ) : (
          /* COMPACT MODERN TABLE GRID */
          <div className="act-table-wrapper">
            <table className="act-table">
              <thead>
                <tr>
                  <th>Thời gian</th>
                  <th>Người thực hiện</th>
                  <th>Hành động</th>
                  <th>Đối tượng</th>
                  <th>Chi tiết</th>
                  <th style={{ width: 40 }}></th>
                </tr>
              </thead>
              <tbody>
                {paginatedRows.map((r) => {
                  const meta = getActionMeta(r.action);
                  const IconComp = meta.icon;
                  const actorName = r.actor_name || "Hệ thống";

                  return (
                    <tr
                      key={r.id}
                      onClick={() => setSelectedRow(r)}
                      className="act-table-row"
                    >
                      <td className="act-td-time">
                        <span className="act-time-rel">{formatRelativeTime(r.created_at)}</span>
                        <span className="act-time-sub">{formatExactTime(r.created_at)}</span>
                      </td>
                      <td>
                        <div className="act-actor-cell">
                          <span className="act-avatar-xs">{getUserInitials(r.actor_name)}</span>
                          <span className="act-actor-name">{actorName}</span>
                        </div>
                      </td>
                      <td>
                        <span className={`act-badge ${meta.badgeClass}`}>
                          <IconComp size={11} />
                          {meta.label}
                        </span>
                      </td>
                      <td>
                        {r.target ? (
                          <span className="act-mono-pill">{r.target}</span>
                        ) : (
                          <span className="act-muted">—</span>
                        )}
                      </td>
                      <td>
                        <FormattedDetail detail={r.detail} />
                      </td>
                      <td>
                        <button
                          type="button"
                          className="act-btn-inspect"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedRow(r);
                          }}
                          title="Xem chi tiết đầy đủ"
                        >
                          <Eye size={12} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* PAGINATION FOOTER */}
        {!loading && filteredRows.length > 0 && (
          <footer className="act-footer">
            <div className="act-footer-info">
              Hiển thị <strong>{(page - 1) * pageSize + 1} - {Math.min(page * pageSize, filteredRows.length)}</strong> / <strong>{filteredRows.length}</strong> bản ghi
            </div>

            <div className="act-footer-nav">
              <label className="act-size-select">
                <span>Dòng/trang:</span>
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setPage(1);
                  }}
                >
                  <option value={15}>15</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                </select>
              </label>

              <div className="act-page-btns">
                <button
                  type="button"
                  className="act-btn-p"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  title="Trang trước"
                >
                  <ChevronLeft size={14} />
                </button>
                <span className="act-page-num">
                  {page} / {totalPages}
                </span>
                <button
                  type="button"
                  className="act-btn-p"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  title="Trang sau"
                >
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>
          </footer>
        )}
      </section>

      {/* INSPECTOR MODAL / DRAWER */}
      {selectedRow && (
        <div className="act-modal-overlay" onClick={() => setSelectedRow(null)}>
          <div className="act-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="act-modal-header">
              <div className="act-modal-title-group">
                <FileText size={18} className="act-modal-icon" />
                <div>
                  <h3 className="act-modal-title">Chi tiết nhật ký #{selectedRow.id}</h3>
                  <span className="act-modal-sub">{formatExactTime(selectedRow.created_at)}</span>
                </div>
              </div>
              <button
                type="button"
                className="act-modal-close"
                onClick={() => setSelectedRow(null)}
                title="Đóng cửa sổ"
              >
                <X size={16} />
              </button>
            </div>

            <div className="act-modal-body">
              <div className="act-modal-grid">
                <div className="act-modal-field">
                  <span className="act-modal-label">Người thực hiện</span>
                  <div className="act-actor-cell">
                    <span className="act-avatar-xs">{getUserInitials(selectedRow.actor_name)}</span>
                    <strong className="act-modal-val">{selectedRow.actor_name || "Hệ thống"}</strong>
                    {selectedRow.actor_user_id && <span className="act-muted-sm">(ID: {selectedRow.actor_user_id})</span>}
                  </div>
                </div>

                <div className="act-modal-field">
                  <span className="act-modal-label">Hành động</span>
                  <div>
                    {selectedMeta && SelectedIcon && (
                      <span className={`act-badge ${selectedMeta.badgeClass}`}>
                        <SelectedIcon size={12} />
                        {selectedMeta.label} ({selectedRow.action})
                      </span>
                    )}
                  </div>
                </div>

                <div className="act-modal-field">
                  <span className="act-modal-label">Đối tượng tác động</span>
                  <div>
                    {selectedRow.target ? (
                      <span className="act-mono-pill">{selectedRow.target}</span>
                    ) : (
                      <span className="act-muted">— Không xác định —</span>
                    )}
                  </div>
                </div>

                <div className="act-modal-field">
                  <span className="act-modal-label">Thời gian tương đối</span>
                  <span className="act-modal-val">{formatRelativeTime(selectedRow.created_at)}</span>
                </div>
              </div>

              <div className="act-modal-section">
                <span className="act-modal-label">Nội dung chi tiết</span>
                <div className="act-modal-detail-box">
                  <FormattedDetail detail={selectedRow.detail} />
                </div>
              </div>

              <div className="act-modal-section">
                <div className="act-modal-label-row">
                  <span className="act-modal-label">Dữ liệu thô (JSON Payload)</span>
                  <button
                    type="button"
                    className="act-btn-ghost-xs"
                    onClick={() => {
                      navigator.clipboard.writeText(JSON.stringify(selectedRow, null, 2));
                      showToast("Đã copy dữ liệu JSON!");
                    }}
                  >
                    <Copy size={11} /> Copy JSON
                  </button>
                </div>
                <pre className="act-json-box">{JSON.stringify(selectedRow, null, 2)}</pre>
              </div>
            </div>

            <div className="act-modal-footer">
              <button
                type="button"
                className="act-btn-compact"
                onClick={() => setSelectedRow(null)}
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
