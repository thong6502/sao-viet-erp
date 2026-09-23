import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  ChevronDown,
  RotateCcw,
  Search,
  SlidersHorizontal,
  Users,
  X,
} from "lucide-react";
import {
  api,
  assetUrl,
  type EmployeeKpis,
  type EmployeeRow,
  type SalaryPreview,
} from "../../../../api/client";
import { EmptyRow } from "../../../../components/EmptyState";
import { Pager, trangHopLe } from "../../../../components/Pager";
import { errText, money } from "../shared/helpers";
import { SalaryModal } from "../modals/SalaryModal";
import "../../../nhan-su.css";
import "../../../luong.css";

export function NhanVienTab({
  token,
  focusEmployeeId,
}: {
  token: string;
  focusEmployeeId?: number;
}) {
  const [emps, setEmps] = useState<EmployeeRow[]>([]);
  const [total, setTotal] = useState(0);
  const [kpis, setKpis] = useState<EmployeeKpis | null>(null);
  const [page, setPage] = useState(1);
  const size = 20;

  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [departments, setDepartments] = useState<{ id: number; name: string }[]>([]);
  const [deptId, setDeptId] = useState<number | undefined>(undefined);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [salaryFilter, setSalaryFilter] = useState<string>("all");

  const [previews, setPreviews] = useState<Record<number, SalaryPreview | null>>({});
  const [picked, setPicked] = useState<EmployeeRow | null>(null);
  const [listErr, setListErr] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(true);

  // Debounce search input (300ms)
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedQ(q);
      setPage(1);
    }, 300);
    return () => clearTimeout(handler);
  }, [q]);

  // Load department metadata for filter dropdown
  useEffect(() => {
    let alive = true;
    api.employees
      .meta(token)
      .then((m) => {
        if (alive) setDepartments(m.departments);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [token]);

  // Fetch employees list from server with pagination & filters
  const load = useCallback(() => {
    setListLoading(true);
    api.employees
      .list(token, {
        page,
        size,
        sort: "code",
        department_id: deptId,
        status: statusFilter || undefined,
        q: debouncedQ.trim() || undefined,
      })
      .then((r) => {
        setEmps(r.items);
        setTotal(r.total);
        setKpis(r.kpis);
        setListErr(null);
        const hopLe = trangHopLe(page, r.total, size);
        if (hopLe !== null) {
          setPage(hopLe);
        }
      })
      .catch((e) => setListErr(errText(e)))
      .finally(() => setListLoading(false));
  }, [token, page, deptId, statusFilter, debouncedQ]);

  useEffect(() => {
    load();
  }, [load]);

  // Asynchronously fetch salary preview for current page visible employees
  useEffect(() => {
    if (!emps.length) return;
    const missing = emps.filter((e) => !(e.id in previews));
    if (!missing.length) return;

    Promise.all(
      missing.map(async (e) => {
        try {
          const prev = await api.luong.salaryPreview(token, e.id);
          return { id: e.id, prev };
        } catch {
          return { id: e.id, prev: null };
        }
      }),
    ).then((results) => {
      setPreviews((curr) => {
        const next = { ...curr };
        for (const r of results) {
          next[r.id] = r.prev;
        }
        return next;
      });
    });
  }, [token, emps, previews]);

  // Liên thông: khi mở từ Hồ sơ NV, tự bật modal lương của NV đó một lần
  const autoOpenedFor = useRef<number | null>(null);
  useEffect(() => {
    if (focusEmployeeId && autoOpenedFor.current !== focusEmployeeId) {
      const e = emps.find((x) => x.id === focusEmployeeId);
      if (e) {
        setPicked(e);
        autoOpenedFor.current = focusEmployeeId;
      } else if (!listLoading) {
        // Nếu NV không nằm ở trang 1, nạp trực tiếp hồ sơ để mở modal
        api.employees
          .get(token, focusEmployeeId)
          .then((d) => {
            setPicked(d);
            autoOpenedFor.current = focusEmployeeId;
          })
          .catch(() => {});
      }
    }
  }, [focusEmployeeId, emps, listLoading, token]);

  // Client-side salary status filter for currently loaded employees
  const shown = emps.filter((e) => {
    if (salaryFilter === "declared") {
      const p = previews[e.id];
      return p && p.monthly > 0;
    }
    if (salaryFilter === "undeclared") {
      const p = previews[e.id];
      return p !== undefined && (!p || p.monthly <= 0);
    }
    return true;
  });

  // KPI strip counts
  const totalStaff = kpis?.total ?? total;
  const workingStaff = kpis
    ? kpis.active + kpis.probation + (kpis.probation_ended ?? 0)
    : emps.filter((e) => e.status === "active" || e.status === "probation").length;
  const daKhaiCount = emps.filter((e) => {
    const p = previews[e.id];
    return p && p.monthly > 0;
  }).length;
  const chuaKhaiCount = emps.filter((e) => {
    const p = previews[e.id];
    return p !== undefined && (!p || p.monthly <= 0);
  }).length;

  return (
    <div>
      {/* 1. KPI Strip / Quick Counters */}
      <div className="lg-emp-kpi-bar" role="group" aria-label="Thống kê nhân sự và lương">
        <button
          type="button"
          className={`lg-emp-kpi-btn ${!statusFilter && salaryFilter === "all" ? "is-active" : ""}`}
          onClick={() => {
            setStatusFilter("");
            setSalaryFilter("all");
            setPage(1);
          }}
          title="Xem tất cả nhân viên"
        >
          <Users size={14} />
          <span>Tổng nhân viên:</span>
          <span className="lg-emp-kpi-val">{totalStaff}</span>
        </button>

        <button
          type="button"
          className={`lg-emp-kpi-btn ${statusFilter === "active" ? "is-active" : ""}`}
          onClick={() => {
            setStatusFilter(statusFilter === "active" ? "" : "active");
            setPage(1);
          }}
          title="Lọc nhân viên đang làm việc"
        >
          <span className="lg-kpi-dot lg-kpi-dot--active" />
          <span>Đang làm việc:</span>
          <span className="lg-emp-kpi-val">{workingStaff}</span>
        </button>

        <button
          type="button"
          className={`lg-emp-kpi-btn ${salaryFilter === "declared" ? "is-active" : ""}`}
          onClick={() => {
            setSalaryFilter(salaryFilter === "declared" ? "all" : "declared");
          }}
          title="Lọc nhân viên đã có mức lương"
        >
          <span className="lg-kpi-dot lg-kpi-dot--declared" />
          <span>Đã khai lương:</span>
          <span className="lg-emp-kpi-val" style={{ color: "#15803d" }}>
            {daKhaiCount}
          </span>
        </button>

        <button
          type="button"
          className={`lg-emp-kpi-btn ${salaryFilter === "undeclared" ? "is-active" : ""}`}
          onClick={() => {
            setSalaryFilter(salaryFilter === "undeclared" ? "all" : "undeclared");
          }}
          title="Lọc nhân viên chưa khai lương"
        >
          <span className="lg-kpi-dot lg-kpi-dot--undeclared" />
          <span>Chưa khai lương:</span>
          <span
            className="lg-emp-kpi-val"
            style={{ color: chuaKhaiCount > 0 ? "#b45309" : undefined }}
          >
            {chuaKhaiCount}
          </span>
        </button>
      </div>

      {/* 2. Toolbar & Filters */}
      <div className="lg-emp-toolbar">
        <div className="lg-emp-search-wrap">
          <Search size={15} className="lg-emp-search-icon" />
          <input
            className="lg-emp-search-input"
            placeholder="Tìm theo họ tên, mã nhân viên…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          {q && (
            <button
              type="button"
              className="lg-emp-search-clear"
              onClick={() => {
                setQ("");
                setDebouncedQ("");
                setPage(1);
              }}
              title="Xoá tìm kiếm"
              aria-label="Xoá tìm kiếm"
            >
              <X size={13} />
            </button>
          )}
        </div>

        <div className="lg-emp-filters">
          {/* Department Filter Dropdown */}
          <div className="lg-emp-select-wrap">
            <select
              className="lg-emp-select"
              value={deptId ?? ""}
              aria-label="Lọc theo phòng/tổ"
              onChange={(e) => {
                setDeptId(e.target.value ? Number(e.target.value) : undefined);
                setPage(1);
              }}
            >
              <option value="">Tất cả phòng / tổ</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
            <ChevronDown size={14} className="lg-emp-select-chevron" />
          </div>

          {/* Employment Status Filter Dropdown */}
          <div className="lg-emp-select-wrap">
            <select
              className="lg-emp-select"
              value={statusFilter}
              aria-label="Lọc theo trạng thái làm việc"
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Tất cả trạng thái</option>
              <option value="active">Chính thức</option>
              <option value="probation">Thử việc</option>
              <option value="probation_ended">Hết thử việc</option>
              <option value="on_leave">Nghỉ phép</option>
              <option value="resigned">Đã thôi việc</option>
            </select>
            <ChevronDown size={14} className="lg-emp-select-chevron" />
          </div>

          {/* Salary Status Filter Dropdown */}
          <div className="lg-emp-select-wrap">
            <select
              className="lg-emp-select"
              value={salaryFilter}
              aria-label="Lọc theo hồ sơ lương"
              onChange={(e) => setSalaryFilter(e.target.value)}
            >
              <option value="all">Tất cả hồ sơ lương</option>
              <option value="declared">Đã khai lương</option>
              <option value="undeclared">Chưa khai lương</option>
            </select>
            <ChevronDown size={14} className="lg-emp-select-chevron" />
          </div>

          {/* Reset Filters button */}
          {(q || deptId != null || statusFilter || salaryFilter !== "all") && (
            <button
              type="button"
              className="lg-emp-btn-reset"
              onClick={() => {
                setQ("");
                setDebouncedQ("");
                setDeptId(undefined);
                setStatusFilter("");
                setSalaryFilter("all");
                setPage(1);
              }}
              title="Đặt lại bộ lọc"
            >
              <RotateCcw size={13} />
              <span>Đặt lại</span>
            </button>
          )}
        </div>
      </div>

      {/* 3. Redesigned Table */}
      <div className="lg-emp-table-wrapper">
        <table className="lg-emp-table">
          <thead>
            <tr>
              <th style={{ width: 100 }}>Mã NV</th>
              <th style={{ minWidth: 200 }}>Nhân viên</th>
              <th style={{ minWidth: 140 }}>Phòng/Tổ</th>
              <th style={{ minWidth: 130 }}>Vị trí</th>
              <th style={{ minWidth: 120 }}>Trạng thái</th>
              <th style={{ minWidth: 150 }}>Mức lương tháng</th>
              <th style={{ minWidth: 130 }}>Đóng BHXH</th>
              <th style={{ width: 140, textAlign: "center" }}>Thao tác</th>
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
                probation_ended: {
                  label: "Hết thử việc",
                  className: "ns-badge ns-badge--due",
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

              const p = previews[e.id];
              const photoSrc = assetUrl(e.photo_url);

              return (
                <tr key={e.id}>
                  {/* Column 1: Mã NV */}
                  <td>
                    <span className="ns-code-chip">{e.code}</span>
                  </td>

                  {/* Column 2: Nhân viên */}
                  <td>
                    <div className="lg-emp-cell-user">
                      {photoSrc ? (
                        <img
                          src={photoSrc}
                          alt={e.full_name}
                          className="lg-emp-avatar"
                          loading="lazy"
                        />
                      ) : (
                        <span className="lg-emp-avatar lg-emp-avatar--initial">
                          {e.full_name.trim().slice(0, 1).toUpperCase()}
                        </span>
                      )}
                      <div className="lg-emp-user-info">
                        <span className="lg-emp-name">{e.full_name}</span>
                        <span className="lg-emp-subtext">
                          {e.position || e.department_name || "Nhân viên"}
                        </span>
                      </div>
                    </div>
                  </td>

                  {/* Column 3: Phòng/Tổ */}
                  <td>
                    {e.department_name ? (
                      <span className="ns-badge ns-badge--muted">
                        {e.department_name}
                      </span>
                    ) : (
                      <span className="lg-zero">—</span>
                    )}
                  </td>

                  {/* Column 4: Vị trí */}
                  <td>{e.position || "—"}</td>

                  {/* Column 5: Trạng thái */}
                  <td>
                    <span className={statusInfo.className}>
                      {statusInfo.label}
                    </span>
                  </td>

                  {/* Column 6: Mức lương tháng */}
                  <td>
                    {p === undefined ? (
                      <span className="cc-card__hint">Đang tải…</span>
                    ) : p && p.monthly > 0 ? (
                      <span className="lg-salary-main font-semibold">
                        {money(p.monthly)} đ
                      </span>
                    ) : (
                      <span className="lg-badge-undeclared">
                        <AlertCircle size={12} />
                        Chưa khai lương
                      </span>
                    )}
                  </td>

                  {/* Column 7: Đóng BHXH */}
                  <td>
                    {p === undefined ? (
                      <span className="cc-card__hint">Đang tải…</span>
                    ) : (p as any)?.insurance_elsewhere ? (
                      <span className="ns-badge ns-badge--info">
                        Đóng nơi khác
                      </span>
                    ) : p && p.insurance_base > 0 ? (
                      <span className="lg-num-val font-semibold">
                        {money(p.insurance_base)} đ
                      </span>
                    ) : (
                      <span className="lg-zero">—</span>
                    )}
                  </td>

                  {/* Column 8: Thao tác */}
                  <td style={{ textAlign: "center" }}>
                    <button
                      type="button"
                      className="lg-btn-salary"
                      onClick={() => setPicked(e)}
                    >
                      <SlidersHorizontal size={14} />
                      <span>Thiết lập lương</span>
                    </button>
                  </td>
                </tr>
              );
            })}

            {shown.length === 0 && (
              <EmptyRow
                colSpan={8}
                trangThai={listErr ? "loi" : listLoading ? "dang-tai" : "rong"}
                loi={listErr}
                onThuLai={load}
                icon="users"
                title={
                  emps.length
                    ? "Không có nhân viên khớp bộ lọc"
                    : "Chưa có nhân viên"
                }
                sub={
                  emps.length
                    ? "Thử thay đổi từ khóa tìm kiếm hoặc bỏ bớt các tiêu chí lọc."
                    : "Khai hồ sơ ở màn Hồ sơ nhân sự trước, rồi quay lại thiết lập lương."
                }
                action={
                  q || deptId || statusFilter || salaryFilter !== "all" ? (
                    <button
                      type="button"
                      className="btn btn--ghost"
                      onClick={() => {
                        setQ("");
                        setDebouncedQ("");
                        setDeptId(undefined);
                        setStatusFilter("");
                        setSalaryFilter("all");
                        setPage(1);
                      }}
                    >
                      Xóa toàn bộ bộ lọc
                    </button>
                  ) : undefined
                }
              />
            )}
          </tbody>
        </table>
      </div>

      {/* 4. Pagination */}
      <Pager
        total={total}
        page={page}
        size={size}
        onPage={setPage}
        loading={listLoading}
        unit="nhân viên"
      />

      {/* Salary Modal */}
      {picked && (
        <SalaryModal
          token={token}
          emp={picked}
          onClose={() => {
            if (picked) {
              setPreviews((curr) => {
                const next = { ...curr };
                delete next[picked.id];
                return next;
              });
            }
            setPicked(null);
            load();
          }}
        />
      )}
    </div>
  );
}
