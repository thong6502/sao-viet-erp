// Hồ sơ nhân sự (module `nhan_su`, lát #1). Danh sách + KPI + Wizard thêm (5 bước) +
// Trang hồ sơ (tab Thông tin / Quá trình công tác / Đính kèm / Nhật ký) + dialog Đổi
// trạng thái / Điều chuyển / Nâng bậc (sinh Quá trình công tác) + nối/tạo tài khoản.
// Backend là cổng quyền thật (403); useCan chỉ ẩn/hiện nút cho gọn UX.
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  api,
  ApiError,
  assetUrl,
  EMPLOYEE_FIELD_MAXLEN,
  PIT_MODE_META,
  type AuditRow,
  type EmployeeAttachment,
  type EmployeeDetail,
  type EmployeeEvent,
  type EmployeeInput,
  type EmployeeKpis,
  type EmployeeMeta,
  type EmployeeRow,
  type EmployeeTransitionInput,
  type JobGrade,
  type Session,
  type UpdateRequest,
  type UserRow,
  type WorkShift,
  type PayrollComponent,
} from "../api/client";
import { Button } from "../components/Button";
import { EmptyRow, EmptyState } from "../components/EmptyState";
import { RowActionButton } from "../components/RowActionButton";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
// `fmtDate` DÙNG CHUNG (utils/format) — trước đây file này tự chép một bản y hệt.
// Đừng viết lại bản cục bộ: sửa cách hiện ngày ở một chỗ mà nửa hệ thống không đổi theo.
import { fmtDate, fmtDateTime, money } from "../utils/format";
import type { NavigateFn } from "../components/AppShell";
import { Timeline, type TimelineEntry } from "../components/Timeline";
import {
  Users,
  Hourglass,
  UserCheck,
  AlertCircle,
  Search,
  Download,
  UserPlus,
  ChevronDown,
  Calendar,
  Briefcase,
  Clock,
  CreditCard,
  FileText,
  Activity,
  Phone,
  Mail,
  MapPin,
  Lock,
  Trash2,
  Edit2,
  TrendingUp,
  UserMinus,
  AlertTriangle,
  ArrowRight,
  Key,
  User,
  Shield,
  Hash,
  X,
  UploadCloud,
  File,
  Image,
  Eye,
} from "lucide-react";
import "./nhan-su.css";

const STATUS_LABEL: Record<string, string> = {
  probation: "Thử việc",
  active: "Chính thức",
  on_leave: "Nghỉ dài hạn",
  suspended: "Đình chỉ",
  resigned: "Đã nghỉ",
};
const STATUS_CLASS: Record<string, string> = {
  probation: "ns-badge--warn",
  active: "ns-badge--ok",
  on_leave: "ns-badge--info",
  suspended: "ns-badge--muted",
  resigned: "ns-badge--danger",
};
const GENDER_LABEL: Record<string, string> = {
  male: "Nam",
  female: "Nữ",
  other: "Khác",
};
const DOC_KIND_LABEL: Record<string, string> = {
  hop_dong: "Hợp đồng",
  cccd: "CCCD",
  bang_cap: "Bằng cấp",
  khac: "Khác",
};
const EVENT_LABEL: Record<string, string> = {
  hired: "Vào làm",
  confirmed: "Chuyển chính thức",
  transferred: "Điều chuyển",
  promoted: "Nâng bậc / đổi chức danh",
  leave_start: "Bắt đầu nghỉ dài hạn",
  leave_end: "Đi làm lại",
  suspended: "Đình chỉ",
  resigned: "Nghỉ việc",
  reinstated: "Tuyển lại",
};

function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  return "Có lỗi xảy ra.";
}

function isEndingSoon(e: EmployeeRow): boolean {
  if (e.status !== "probation" || !e.probation_end_date) return false;
  const end = new Date(e.probation_end_date).getTime();
  const now = Date.now();
  return end >= now && end <= now + 30 * 24 * 3600 * 1000; // khớp KPI backend (30 ngày)
}

function getAvatarClass(name: string): string {
  const firstChar = name.trim().slice(0, 1).toLowerCase();
  const validChars = [
    "a",
    "b",
    "c",
    "d",
    "e",
    "g",
    "h",
    "k",
    "l",
    "m",
    "n",
    "p",
    "q",
    "s",
    "t",
    "u",
    "v",
    "x",
  ];
  if (validChars.includes(firstChar)) return `ns2-row__av--${firstChar}`;
  return "ns2-row__av--default";
}

// --- Bậc tay nghề (danh mục `job_grades`) ----------------------------------
// Bậc CHỈ để khai: không mang tiền, không hệ số. Chỉ khối SẢN XUẤT mới khai.

/** Có hiện ô "Bậc tay nghề" cho phòng/tổ này không. `la_san_xuat` là cờ HIỆU LỰC — backend đã
 *  leo cây cha-con nên FE không phải tự suy. Chưa ai tick cờ ở đâu ⇒ hiện cho MỌI phòng: thà
 *  thừa một ô còn hơn giấu mất đường khai bậc của cả nhà máy. */
function isProduction(
  meta: EmployeeMeta | null,
  deptId: number | null | undefined,
): boolean {
  if (!meta) return false;
  const marked = meta.departments.some((d) => d.la_san_xuat);
  if (!marked) return true;
  return meta.departments.find((d) => d.id === deptId)?.la_san_xuat ?? false;
}

/** Danh mục bậc dùng chung cho wizard / dialog nâng bậc / điều chuyển.
 *  Để LOCAL trong file chứ không nâng thành prop của `EmployeeWizard`: màn Phòng ban cũng dựng
 *  wizard này, thêm một prop bắt buộc là vỡ chỗ đó. */
function useJobGrades(token: string) {
  const [grades, setGrades] = useState<JobGrade[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const reload = useCallback(() => {
    setErr(null);
    return api.employees
      .jobGrades(token, { active_only: true })
      .then((r) => setGrades(r.items))
      .catch((e) => {
        setGrades(null);
        setErr(errMsg(e));
      });
  }, [token]);
  useEffect(() => {
    void reload();
  }, [reload]);
  /** Trả BẢN GHI vừa tạo để nơi gọi chọn luôn bậc đó — thêm xong mà còn phải tự tìm lại trong
   *  danh sách là thừa một bước, và dễ chọn nhầm bậc tên gần giống. */
  const addGrade = useCallback(
    async (name: string): Promise<JobGrade> => {
      const g = await api.employees.createJobGrade(token, { name });
      await reload();
      return g;
    },
    [token, reload],
  );
  return { grades, err, reload, addGrade };
}

/** Ô chọn bậc + thêm bậc TẠI CHỖ.
 *  KHÔNG bọc bằng `Field`: `Field` render `<label>`, mà `<label>` nuốt click của nút bên trong
 *  (bấm "+ Thêm bậc" sẽ nhảy focus vào select thay vì mở ô nhập).
 *  ⚠ Nơi gọi TUYỆT ĐỐI không preselect `emp.job_grade_id`: danh sách chỉ có bậc đang BẬT, người
 *  đang mang bậc đã tắt sẽ bị select nhảy về option đầu rồi ÂM THẦM đổi bậc lúc Lưu. */
function JobGradeField({
  grades,
  err,
  reload,
  addGrade,
  value,
  onChange,
  label,
  hint,
  allowKeep,
  canCreate,
}: {
  grades: JobGrade[] | null;
  err: string | null;
  reload: () => void;
  addGrade: (name: string) => Promise<JobGrade>;
  value: number | null;
  onChange: (id: number | null) => void;
  label: string;
  hint?: string;
  allowKeep?: boolean;
  canCreate: boolean;
}) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [addErr, setAddErr] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);
  const loading = grades === null && err == null;

  function cancelAdd() {
    setAdding(false);
    setName("");
    setAddErr(null);
  }

  async function saveGrade() {
    const n = name.trim();
    if (!n) return;
    setBusy(true);
    setAddErr(null);
    try {
      const g = await addGrade(n);
      onChange(g.id);
      setAdded(g.name);
      setAdding(false);
      setName("");
    } catch (e) {
      // Trùng tên là lỗi hay gặp nhất → GIỮ NGUYÊN ô nhập để sửa vài ký tự, đừng bắt gõ lại.
      setAddErr(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ns-field">
      <span className="ns-field__label">{label}</span>
      <div className="ns-inline-add">
        <select
          value={value ?? ""}
          disabled={loading || err != null}
          onChange={(e) => {
            setAdded(null);
            onChange(e.target.value === "" ? null : Number(e.target.value));
          }}
        >
          <option value="">
            {loading
              ? "Đang tải danh mục bậc…"
              : err != null
                ? "Không tải được danh mục bậc"
                : allowKeep
                  ? "— giữ nguyên —"
                  : "— chưa khai —"}
          </option>
          {(grades ?? []).map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
        {/* {canCreate && !adding && (
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => {
              setAdding(true);
              setAddErr(null);
              setAdded(null);
            }}
          >
            + Thêm bậc
          </button>
        )} */}
      </div>

      {adding && (
        <div className="ns-inline-add">
          <input
            autoFocus
            value={name}
            placeholder="Tên bậc, vd: Bậc 4"
            onChange={(e) => setName(e.target.value)}
            // Ô này nằm TRONG modal: không chặn nổi bọt thì Esc đóng luôn cả wizard, mất sạch
            // những gì đang gõ dở ở các bước trước.
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                e.stopPropagation();
                void saveGrade();
              }
              if (e.key === "Escape") {
                e.stopPropagation();
                cancelAdd();
              }
            }}
          />
          <button
            type="button"
            className="btn btn--primary btn--sm"
            disabled={busy || !name.trim()}
            onClick={() => void saveGrade()}
          >
            {busy ? "Đang lưu…" : "Lưu bậc"}
          </button>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            disabled={busy}
            onClick={cancelAdd}
          >
            Hủy
          </button>
        </div>
      )}

      {addErr && (
        <span className="ns-field__hint ns-field__hint--err">{addErr}</span>
      )}
      {err != null && (
        <span className="ns-field__hint ns-field__hint--err">
          Không tải được danh mục bậc ({err}).{" "}
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={reload}
          >
            Thử lại
          </button>
        </span>
      )}
      {added && (
        <span className="ns-field__hint">Đã thêm “{added}” vào danh mục.</span>
      )}
      {err == null && !loading && grades?.length === 0 && !adding && (
        <span className="ns-field__hint">
          {canCreate
            ? "Danh mục bậc đang trống — bấm “+ Thêm bậc” để khai."
            : "Danh mục bậc đang trống — nhờ HCNS khai bậc trước."}
        </span>
      )}
      {hint && <span className="ns-field__hint">{hint}</span>}
    </div>
  );
}

export function NhanSuPage({ navigate }: { navigate?: NavigateFn }) {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("nhan_su", "create");
  const canApprove = can("nhan_su", "approve");
  const canSalary = can("nhan_su", "edit_salary"); // có quyền khai lương → hiện bước "Lương" khi thêm NV
  // Ô "Xuất Excel danh sách". Trước 11/08/2026 nút render TRẦN, không hỏi quyền gì — nên ô đó
  // trong ma trận chưa bao giờ có tác dụng. Máy chủ cũng đã siết sang `nhan_su:export`.
  const canExport = can("nhan_su", "export");

  const [data, setData] = useState<{
    items: EmployeeRow[];
    total: number;
    kpis: EmployeeKpis;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  /** Lỗi THAO TÁC (vd xuất Excel hỏng) → chỉ hiện băng đỏ, bảng vẫn còn dữ liệu. */
  const [error, setError] = useState<string | null>(null);
  /** Lỗi TẢI DANH SÁCH → mới được phép thay chỗ của bảng bằng khối "không đọc được".
   *  ⚠ Đừng gộp hai ô nhớ này làm một: gộp rồi thì một lần xuất Excel hỏng cũng làm cả
   *  bảng nhân sự biến mất, người dùng tưởng mất dữ liệu. */
  const [listError, setListError] = useState<string | null>(null);

  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [deptFilter, setDeptFilter] = useState<number | "">("");
  const [accountFilter, setAccountFilter] = useState(""); // "" | "yes" | "no"
  const [sort, setSort] = useState("code");
  const [endingSoon, setEndingSoon] = useState(false); // KPI "sắp hết thử việc" (lọc client)
  const [exporting, setExporting] = useState(false);
  const [page, setPage] = useState(1);
  const size = 20;

  const [meta, setMeta] = useState<EmployeeMeta | null>(null);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [reqOpen, setReqOpen] = useState(false);
  const [reqCount, setReqCount] = useState(0);

  const loadReqs = useCallback(() => {
    if (!token || !canApprove) return;
    api.employees
      .updateRequests(token, "pending")
      .then((r) => setReqCount(r.items.length))
      .catch(() => setReqCount(0));
  }, [token, canApprove]);
  useEffect(() => {
    loadReqs();
  }, [loadReqs]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    api.employees
      .list(token, {
        q: q || undefined,
        status: statusFilter || undefined,
        department_id: deptFilter === "" ? undefined : deptFilter,
        has_account: accountFilter === "" ? undefined : accountFilter === "yes",
        sort,
        page,
        size,
      })
      .then((res) => {
        setData({ items: res.items, total: res.total, kpis: res.kpis });
        setListError(null);
      })
      .catch((e) => setListError(errMsg(e)))
      .finally(() => setLoading(false));
  }, [token, q, statusFilter, deptFilter, accountFilter, sort, page]);

  /** Tải file .xlsx do MÁY CHỦ dựng.
   *
   *  Trước 08/08/2026 hàm này tự nối chuỗi CSV ngay trên trình duyệt, đặt tên nút là "Xuất Excel"
   *  nhưng file ra là `.csv`, và tệ nhất: nó chỉ lấy **200 người đầu** rồi im lặng — ai đứng thứ
   *  201 trở đi biến mất khỏi file mà không có một dòng cảnh báo nào.
   *
   *  Bản mới gửi ĐÚNG bộ lọc đang chọn lên máy chủ; máy chủ lấy trọn theo phạm vi quyền của người
   *  bấm, nên số dòng trong file luôn khớp số "Tổng" trên màn. */
  async function exportExcel() {
    if (!token) return;
    setExporting(true);
    try {
      const url = await api.employees.exportXlsxBlobUrl(token, {
        q: q || undefined,
        status: statusFilter || undefined,
        department_id: deptFilter === "" ? undefined : deptFilter,
        sort,
      });
      const a = document.createElement("a");
      a.href = url;
      a.download = "danh-sach-nhan-vien.xlsx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setError("Không tải được file danh sách nhân viên.");
    } finally {
      setExporting(false);
    }
  }

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (token)
      api.employees
        .meta(token)
        .then(setMeta)
        .catch(() => setMeta(null));
  }, [token]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / size)) : 1;
  const rows = (data?.items ?? []).filter(
    (e) => !endingSoon || isEndingSoon(e),
  );

  return (
    <main className="ns ns2">
      <header className="ns__head">
        <div>
          {/* Eyebrow = TÊN SECTION trên sidebar, chép nguyên văn, MỘT cấp. Lớp phải là
              `eyebrow` (global.css) — `ns__eyebrow` không có CSS ở đâu cả, dùng nó là ra
              chữ thường 15px. */}
          <p className="eyebrow">Nhân sự &amp; Lương</p>
          <h1 className="ns__title">Hồ sơ nhân sự</h1>
          <p className="ns__sub">
            Phòng Hành chính nhân sự · quản lý hồ sơ, quá trình công tác
          </p>
        </div>
        <div className="ns2__headact">
          {/* Vai PHỤ → ghost. Cùng hệ `.btn` với nút cam bên cạnh nên hai nút bằng chiều cao;
              trước đây nút này cao 40px (`ns-btn-secondary`) còn nút kia 40px tự chế — đổi một
              cái sang `.btn` mà giữ cái kia là lệch hàng ngay. */}
          {canApprove && (
            <Button
              type="button"
              variant="ghost"
              className={reqCount > 0 ? "ns2-reqbtn--on" : undefined}
              onClick={() => setReqOpen(true)}
            >
              <Activity size={14} />
              Yêu cầu cập nhật{reqCount > 0 ? ` (${reqCount})` : ""}
            </Button>
          )}
          {/* Hành động chính DUY NHẤT của màn → `accent` (cam). ⚠ `variant="primary"` trong code
              này ra màu NAVY, ngược với tên gọi trong docs/UI_DESIGN.md. */}
          {canCreate && (
            <Button
              type="button"
              variant="accent"
              onClick={() => setWizardOpen(true)}
            >
              <UserPlus size={15} />
              Thêm nhân viên
            </Button>
          )}
        </div>
      </header>

      <div className="ns2__grid">
        <section className="ns2__list">
          {/* Dải lọc nhanh + thanh lọc nằm CHUNG một khung: chúng là một việc
              (thu hẹp danh sách), không phải hai khối rời cần hai lớp viền. */}
          <div className="ns2__controls">
          {data && (
            <KpiStrip
              kpis={data.kpis}
              statusFilter={statusFilter}
              endingSoon={endingSoon}
              onPickAll={() => {
                setEndingSoon(false);
                setStatusFilter("");
              }}
              onPickProbation={() => {
                setEndingSoon(false);
                setStatusFilter("probation");
              }}
              onPickActive={() => {
                setEndingSoon(false);
                setStatusFilter("active");
              }}
              onPickEndingSoon={() => {
                setStatusFilter("probation");
                setEndingSoon(true);
              }}
            />
          )}

          <div className="ns2__toolbar">
            <div className="ns-search-wrapper">
              <Search className="ns-search-icon" size={16} />
              <input
                className="ns__search"
                placeholder="Tìm tên / mã…"
                value={q}
                onChange={(e) => {
                  setPage(1);
                  setEndingSoon(false);
                  setQ(e.target.value);
                }}
              />
              {q && (
                <button
                  type="button"
                  style={{
                    position: "absolute",
                    right: "10px",
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: "#94a3b8",
                    display: "flex",
                    alignItems: "center",
                    padding: 0,
                  }}
                  onClick={() => {
                    setQ("");
                    setPage(1);
                  }}
                  title="Xóa tìm kiếm"
                >
                  <X size={14} />
                </button>
              )}
            </div>
            <div className="ns2__filters">
              <div className="ns-select-wrapper">
                <select
                  value={statusFilter}
                  onChange={(e) => {
                    setPage(1);
                    setEndingSoon(false);
                    setStatusFilter(e.target.value);
                  }}
                >
                  <option value="">Mọi trạng thái</option>
                  {Object.entries(STATUS_LABEL).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
                <ChevronDown className="ns-select-chevron" size={14} />
              </div>
              <div className="ns-select-wrapper">
                <select
                  value={deptFilter}
                  onChange={(e) => {
                    setPage(1);
                    setDeptFilter(
                      e.target.value === "" ? "" : Number(e.target.value),
                    );
                  }}
                >
                  <option value="">Mọi phòng/tổ</option>
                  {meta?.departments.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
                <ChevronDown className="ns-select-chevron" size={14} />
              </div>
              <div className="ns-select-wrapper">
                <select
                  value={accountFilter}
                  onChange={(e) => {
                    setPage(1);
                    setEndingSoon(false);
                    setAccountFilter(e.target.value);
                  }}
                  title="Lọc theo tài khoản đăng nhập"
                >
                  <option value="">Tài khoản: tất cả</option>
                  <option value="yes">Có tài khoản</option>
                  <option value="no">Chưa có tài khoản</option>
                </select>
                <ChevronDown className="ns-select-chevron" size={14} />
              </div>
              <div className="ns-select-wrapper">
                <select
                  value={sort}
                  onChange={(e) => {
                    setPage(1);
                    setSort(e.target.value);
                  }}
                  title="Sắp xếp"
                >
                  <option value="code">Mã ↑</option>
                  <option value="full_name">Tên A→Z</option>
                  <option value="-hire_date">Mới vào trước</option>
                  <option value="hire_date">Vào lâu trước</option>
                  <option value="status">Trạng thái</option>
                </select>
                <ChevronDown className="ns-select-chevron" size={14} />
              </div>
              {canExport && (
                <button
                  className="ns-btn-excel"
                  onClick={exportExcel}
                  disabled={exporting}
                >
                  <Download size={14} />
                  {exporting ? "Đang xuất…" : "Xuất Excel"}
                </button>
              )}
              {/* Bỏ chip "Sắp hết thử việc ×": dải lọc phía trên đã sáng đúng ô đó rồi,
                  hai chỗ báo cùng một trạng thái chỉ làm người dùng phải đọc hai lần. */}
            </div>
          </div>
          </div>

          {error && (
            <div className="banner banner--error" role="alert">
              {error}
            </div>
          )}

          <div className="ns-table-wrapper">
            <table className="ns-table-records">
              <thead>
                <tr>
                  <th>Mã NV</th>
                  <th>Nhân viên</th>
                  <th>Phòng/Tổ</th>
                  <th>Chức danh</th>
                  <th>Bậc tay nghề</th>
                  <th>Ngày vào làm</th>
                  <th>Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {loading && <EmptyRow colSpan={7} trangThai="dang-tai" />}
                {!loading && listError && (
                  <EmptyRow
                    colSpan={7}
                    trangThai="loi"
                    loi={listError}
                    onThuLai={load}
                  />
                )}
                {!loading &&
                  !listError &&
                  rows.map((e) => {
                    const avatarClass = getAvatarClass(e.full_name);
                    const photoSrc = assetUrl(e.photo_url);
                    return (
                      <tr
                        key={e.id}
                        className="ns-table-row"
                        onClick={() => setSelectedId(e.id)}
                      >
                        <td className="ns-cell-code">
                          <span className="ns-code-chip">{e.code}</span>
                        </td>
                        <td>
                          <div className="ns-cell-employee">
                            <div className="ns-avatar-wrapper">
                              {/* CÓ ảnh thì hiện ảnh, KHÔNG có thì mới rơi về chữ cái.
                                  Trước đây danh sách luôn vẽ chữ cái dù hồ sơ đã có ảnh — trong
                                  khay chi tiết thì lại hiện ảnh, nên cùng một người ra hai mặt
                                  khác nhau ở hai chỗ. `photo_url` vốn đã có trong `EmployeeRow`
                                  của API và class `.ns-table-avatar-img` cũng đã có sẵn trong CSS;
                                  chỉ thiếu đúng nhánh này. */}
                              {photoSrc ? (
                                <img
                                  src={photoSrc}
                                  alt={e.full_name}
                                  className="ns-table-avatar-img"
                                  loading="lazy"
                                />
                              ) : (
                                <span className={`ns-table-avatar ${avatarClass}`}>
                                  {e.full_name.trim().slice(0, 1).toUpperCase()}
                                </span>
                              )}
                              <span
                                className={`ns-avatar-dot ns-avatar-dot--${e.status}`}
                                title={`Trạng thái: ${STATUS_LABEL[e.status] ?? e.status}`}
                              />
                            </div>
                            <span className="ns-cell-name">
                              {e.full_name}
                              {e.account_username && (
                                <span title={`Tài khoản: ${e.account_username}`}>
                                  <Key
                                    size={13}
                                    style={{ marginLeft: "2px" }}
                                  />
                                </span>
                              )}
                            </span>
                          </div>
                        </td>
                        <td className="ns-cell-dept">{e.department_name ?? "—"}</td>
                        <td className="ns-cell-title">{e.role_name ?? e.position ?? "—"}</td>
                        {/* Rơi về `job_grade` = bậc kiểu CŨ (chữ tự gõ, chưa vào danh mục) —
                          nói rõ ở tooltip để HCNS biết vì sao người này không sửa bậc được. */}
                        <td
                          title={
                            e.job_grade_name == null && e.job_grade != null
                              ? "Bậc kiểu cũ (chữ) — dùng Nâng bậc để chuyển sang danh mục."
                              : undefined
                          }
                        >
                          {e.job_grade_name || e.job_grade ? (
                            <span className="ns-grade-chip">
                              {e.job_grade_name ?? e.job_grade}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="ns-cell-date">{fmtDate(e.hire_date)}</td>
                        <td>
                          <StatusBadge status={e.status} />
                        </td>
                      </tr>
                    );
                  })}
                {!loading && !listError && rows.length === 0 && (
                  <EmptyRow
                    colSpan={7}
                    icon="users"
                    title={
                      endingSoon
                        ? "Chưa có ai sắp hết thử việc"
                        : "Chưa có nhân viên nào khớp"
                    }
                    sub={
                      endingSoon
                        ? "Danh sách này chỉ hiện người còn dưới ngưỡng ngày tới hạn thử việc."
                        : "Thử bỏ bớt bộ lọc, hoặc thêm nhân viên mới."
                    }
                  />
                )}
              </tbody>
            </table>
          </div>

          {/* Chân bảng chuẩn: TỔNG bên trái, nút chuyển trang bên phải và CHỈ hiện khi có
              hơn 1 trang — một cặp ‹ › mờ tịt dưới bảng 3 dòng chỉ làm người dùng đi tìm
              trang thứ hai không tồn tại. */}
          <div className="ns__pager">
            <span>{data ? `${data.total} nhân viên` : ""}</span>
            {totalPages > 1 && (
              <div className="ns__pagerbtns">
                <button
                  type="button"
                  className="btn btn--ghost"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  ‹
                </button>
                <span>
                  {page} / {totalPages}
                </span>
                <button
                  type="button"
                  className="btn btn--ghost"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  ›
                </button>
              </div>
            )}
          </div>
        </section>
      </div>

      {selectedId != null && (
        <div
          className="ns-modal"
          role="dialog"
          aria-modal="true"
          onClick={() => setSelectedId(null)}
        >
          <div
            className="ns-detail-modal-box"
            onClick={(e) => e.stopPropagation()}
          >
            <EmployeeDetailPanel
              token={token!}
              employeeId={selectedId}
              meta={meta}
              navigate={navigate}
              onClose={() => setSelectedId(null)}
              onChanged={load}
            />
          </div>
        </div>
      )}

      {wizardOpen && meta && (
        <EmployeeWizard
          token={token!}
          meta={meta}
          canSalary={canSalary}
          onClose={() => setWizardOpen(false)}
          onCreated={(id) => {
            setWizardOpen(false);
            load();
            setSelectedId(id);
          }}
        />
      )}

      {reqOpen && (
        <RequestQueueModal
          token={token!}
          onClose={() => setReqOpen(false)}
          onDecided={() => {
            loadReqs();
            if (selectedId) load();
          }}
        />
      )}
    </main>
  );
}

// Hàng đợi HCNS duyệt "yêu cầu cập nhật" của NV.
const REQ_FIELD_LABEL: Record<string, string> = {
  full_name: "Họ tên",
  date_of_birth: "Ngày sinh",
  national_id: "CCCD",
  national_id_date: "Ngày cấp CCCD",
  national_id_place: "Nơi cấp CCCD",
  permanent_address: "Hộ khẩu",
  bank_account: "Số tài khoản",
  bank_name: "Ngân hàng",
  dependents_count: "Người phụ thuộc",
};
const REQ_DATE_FIELDS = new Set(["date_of_birth", "national_id_date"]);

/** Một giá trị trong đề nghị → chuỗi đọc được. `null`/rỗng phải nói RÕ là "chưa có" hay "bỏ
 *  trống" chứ không in ô trắng: người duyệt đang phải quyết dựa trên đúng mấy chữ này. */
function reqValue(field: string, v: unknown, khiRong: string): string {
  if (v === null || v === undefined || v === "") return khiRong;
  return REQ_DATE_FIELDS.has(field) ? fmtDate(String(v)) : String(v);
}

/** Ô nào vượt độ dài cột hồ sơ ⇒ bấm Duyệt chắc chắn bị BE chặn. Nói trước cho người duyệt
 *  (và tắt nút Duyệt) thay vì để họ bấm rồi ăn thông báo lỗi. */
function reqQuaDai(changes: UpdateRequest["changes"]): string[] {
  const loi: string[] = [];
  for (const [k, v] of Object.entries(changes)) {
    const max = EMPLOYEE_FIELD_MAXLEN[k];
    if (max && typeof v === "string" && v.length > max) {
      loi.push(`${REQ_FIELD_LABEL[k] ?? k}: ${v.length} ký tự, vượt giới hạn ${max}`);
    }
  }
  return loi;
}

function RequestQueueModal({
  token,
  onClose,
  onDecided,
}: {
  token: string;
  onClose: () => void;
  onDecided: () => void;
}) {
  const [items, setItems] = useState<UpdateRequest[] | null>(null);
  const [busy, setBusy] = useState(false);
  /** Lỗi TẢI hàng đợi. Trước đây `.catch` nuốt lỗi rồi `setItems([])` ⇒ máy chủ chết mà bảng
   *  vẫn in "không có yêu cầu": HCNS tưởng sạch việc và đóng màn. */
  const [listError, setListError] = useState<string | null>(null);
  /** Lỗi khi DUYỆT/TỪ CHỐI (khác lỗi tải danh sách) — vd nội dung dài hơn ô hồ sơ. */
  const [actionError, setActionError] = useState<string | null>(null);
  const load = useCallback(() => {
    setListError(null);
    api.employees
      .updateRequests(token, "pending")
      .then((r) => setItems(r.items))
      .catch((e) => {
        setItems([]);
        setListError(errMsg(e));
      });
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

  async function decide(id: number, approve: boolean) {
    setBusy(true);
    setActionError(null);
    try {
      if (approve) await api.employees.approveRequest(token, id);
      else await api.employees.rejectRequest(token, id, "Từ chối");
      load();
      onDecided();
    } catch (e) {
      // Trước đây lỗi duyệt rơi vào hư không: người duyệt bấm, không thấy gì đổi, tưởng máy
      // đơ. Hay gặp nhất là ô dài hơn cột (BE trả câu "… tối đa N ký tự").
      setActionError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true" aria-labelledby="nsq-title">
      <div className="ns-modal__box ns-modal__box--wide">
        <header className="ns-modal__head">
          <h2 id="nsq-title">Yêu cầu cập nhật hồ sơ (chờ duyệt)</h2>
          <button className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {actionError && (
            <div className="banner banner--error" role="alert">
              {actionError}
            </div>
          )}
          {!items && !listError && <EmptyState trangThai="dang-tai" inline />}
          {listError && (
            <EmptyState trangThai="loi" loi={listError} onThuLai={load} inline />
          )}
          {!listError && items?.length === 0 && (
            <EmptyState
              icon="clipboard"
              title="Chưa có yêu cầu chờ duyệt"
              sub="Nhân viên gửi đề nghị sửa hồ sơ thì việc sẽ hiện ở đây."
              inline
            />
          )}
          {/* MỖI ĐỀ NGHỊ MỘT THẺ, không nhồi vào một ô bảng nữa: chuỗi nối bằng dấu "·" không
              xuống dòng nên hộ khẩu / nơi cấp CCCD dài là đẩy luôn cột Lý do và hai nút
              Duyệt–Từ chối ra khỏi màn. Thẻ cũng là chỗ đặt được cột "Hiện tại" — người duyệt
              phải thấy đang đổi TỪ GÌ sang gì mới quyết được. */}
          {!listError && !!items?.length && (
            <ul className="nsq__list">
              {items.map((r) => {
                const entries = Object.entries(r.changes);
                const quaDai = reqQuaDai(r.changes);
                return (
                  <li className="nsq__item" key={r.id}>
                    <div className="nsq__head">
                      <span className="nsq__who">
                        <User size={13} />
                        {r.employee_name ?? `NV#${r.employee_id}`}
                      </span>
                      <span className="nsq__sent">
                        <Clock size={12} />
                        Gửi {fmtDateTime(r.created_at)}
                      </span>
                    </div>

                    <div className="nsq__diff">
                      <div className="nsq__diff-head">
                        <span>Mục thông tin</span>
                        <span>Hiện tại</span>
                        <span aria-hidden="true" />
                        <span>Đề nghị mới</span>
                      </div>
                      {entries.map(([k, v]) => (
                        <div className="nsq__diff-row" key={k}>
                          <span className="nsq__diff-name">
                            {REQ_FIELD_LABEL[k] ?? k}
                          </span>
                          <span className="nsq__chip nsq__chip--old">
                            {reqValue(k, r.current?.[k], "(chưa có)")}
                          </span>
                          <ArrowRight
                            size={13}
                            className="nsq__arrow"
                            aria-hidden="true"
                          />
                          <span className="nsq__chip nsq__chip--new">
                            {reqValue(k, v, "(bỏ trống)")}
                          </span>
                        </div>
                      ))}
                    </div>

                    {r.reason && (
                      <p className="nsq__reason">
                        <span className="nsq__reason-label">Lý do đề nghị:</span>{" "}
                        {r.reason}
                      </p>
                    )}

                    {quaDai.length > 0 && (
                      <p className="nsq__warn" role="alert">
                        <AlertTriangle size={13} />
                        <span>
                          Nội dung dài hơn ô hồ sơ cho phép ({quaDai.join(" · ")}) — duyệt
                          sẽ bị chặn. Đề nghị nhân viên gửi lại bản ngắn gọn.
                        </span>
                      </p>
                    )}

                    <div className="nsq__foot">
                      <div className="cc-rowact ns-rowact">
                        <RowActionButton
                          dense
                          label="Duyệt"
                          icon="check"
                          disabled={busy || quaDai.length > 0}
                          onClick={() => decide(r.id, true)}
                        />
                        {/* GIỮ tín hiệu nguy hiểm: từ chối là quyết định NV nhận được ngay,
                            mất màu đỏ là bấm nhầm ô bên cạnh. */}
                        <RowActionButton
                          dense
                          danger
                          label="Từ chối"
                          icon="ban"
                          disabled={busy}
                          onClick={() => decide(r.id, false)}
                        />
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose}>
            Đóng
          </button>
        </footer>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const dotBg =
    status === "active"
      ? "#16a34a"
      : status === "probation"
      ? "#d97706"
      : status === "on_leave"
      ? "#9333ea"
      : status === "resigned"
      ? "#dc2626"
      : "#9ca3af";

  return (
    <span className={`ns-badge ${STATUS_CLASS[status] ?? "ns-badge--muted"}`}>
      <span className="ns-badge-dot" style={{ backgroundColor: dotBg }} />
      <span>{STATUS_LABEL[status] ?? status}</span>
    </span>
  );
}

function KpiStrip({
  kpis,
  statusFilter,
  endingSoon,
  onPickAll,
  onPickProbation,
  onPickActive,
  onPickEndingSoon,
}: {
  kpis: EmployeeKpis;
  statusFilter: string;
  endingSoon: boolean;
  onPickAll: () => void;
  onPickProbation: () => void;
  onPickActive: () => void;
  onPickEndingSoon: () => void;
}) {
  const isAllActive = statusFilter === "" && !endingSoon;
  const isProbationActive = statusFilter === "probation" && !endingSoon;
  const isActiveActive = statusFilter === "active" && !endingSoon;
  const isEndingSoonActive = endingSoon;

  // "Sắp hết thử việc" = 0 thì KHÔNG tô cảnh báo: màu để dành cho lúc thật sự có việc.
  const endingSoonCount = kpis.probation_ending_soon;

  return (
    <div className="ns2__kpis" role="group" aria-label="Lọc nhanh theo trạng thái">
      <button
        type="button"
        className={`ns__kpi${isAllActive ? " is-active" : ""}`}
        onClick={onPickAll}
        aria-pressed={isAllActive}
        title="Xem tất cả nhân sự"
      >
        <Users size={13} aria-hidden="true" />
        <span className="ns__kpilabel">Tất cả</span>
        <span className="ns__kpival">{kpis.total}</span>
      </button>

      <button
        type="button"
        className={`ns__kpi${isProbationActive ? " is-active" : ""}`}
        onClick={onPickProbation}
        aria-pressed={isProbationActive}
        title="Chỉ xem người đang thử việc"
      >
        <Hourglass size={13} aria-hidden="true" />
        <span className="ns__kpilabel">Thử việc</span>
        <span className="ns__kpival">{kpis.probation}</span>
      </button>

      <button
        type="button"
        className={`ns__kpi${isActiveActive ? " is-active" : ""}`}
        onClick={onPickActive}
        aria-pressed={isActiveActive}
        title="Chỉ xem người đã chính thức"
      >
        <UserCheck size={13} aria-hidden="true" />
        <span className="ns__kpilabel">Chính thức</span>
        <span className="ns__kpival">{kpis.active}</span>
      </button>

      {/* Tách sang phải: đây là ô DUY NHẤT đòi người làm gì đó, không xếp lẫn 3 ô đếm kia. */}
      <button
        type="button"
        className={`ns__kpi ${isEndingSoonActive ? " is-active" : ""}`}
        onClick={onPickEndingSoon}
        aria-pressed={isEndingSoonActive}
        title={
          endingSoonCount === 0
            ? "Chưa có ai sắp hết thử việc trong 30 ngày tới"
            : `${endingSoonCount} người hết thử việc trong 30 ngày tới — cần quyết định ký chính thức`
        }
      >
        <AlertCircle size={13} aria-hidden="true" />
        <span className="ns__kpilabel">Sắp hết thử việc</span>
        <span className="ns__kpival">{endingSoonCount}</span>
      </button>
    </div>
  );
}

// --- Wizard thêm nhân viên (5 bước) ----------------------------------------

export function EmployeeWizard({
  token,
  meta,
  canSalary,
  onClose,
  onCreated,
  initialDepartmentId,
}: {
  token: string;
  meta: EmployeeMeta;
  canSalary: boolean;
  onClose: () => void;
  onCreated: (id: number) => void;
  // Chọn sẵn tổ khi mở từ màn Phòng ban (khỏi chọn lại). Bỏ trống → tổ đầu danh sách như cũ.
  initialDepartmentId?: number | null;
}) {
  const STEPS = [
    "Định danh & việc làm",
    "Cá nhân",
    "Lương & BHXH",
    "Đính kèm",
    "Tài khoản",
  ];
  const can = useCan();
  const canCreateGrade = can("nhan_su", "create");
  const jg = useJobGrades(token);
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<EmployeeInput>({
    full_name: "",
    department_id: initialDepartmentId ?? meta.departments[0]?.id ?? null,
    status: "probation",
    hire_date: new Date().toISOString().slice(0, 10),
    dependents_count: 0,
  });
  const [files, setFiles] = useState<{ file: File; doc_kind: string }[]>([]);
  const [makeAccount, setMakeAccount] = useState(false);
  const [acc, setAcc] = useState({
    username: "",
    password: "",
    role_id: "" as number | "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Lương cơ bản = mức đóng BH; các khoản phụ cấp là số cố định khai riêng từng nhân viên.
  const [luongViTri, setLuongViTri] = useState(0);
  const [luongTrachNhiem, setLuongTrachNhiem] = useState(0);
  // "Lương trả 1 lần" (đợt 1): mức trả trong MỘT lần — số điền sẵn khi lập phiếu đợt 1 ở màn Lương.
  const [luongDot1, setLuongDot1] = useState(0);
  // % hoa hồng NV kinh doanh — nhập theo PHẦN TRĂM ở UI, gửi lên là PHÂN SỐ. Chỉ để KHAI:
  // engine lương không tự cộng khoản này.
  const [commissionPct, setCommissionPct] = useState(0);
  // Khoản thu nhập chọn từ DANH MỤC (Tầng 1 → Tầng 2). Giữ ở state cục bộ tới lúc tạo xong hồ
  // sơ mới gán được — API gán khoản cần `employee_id` mà lúc này chưa có.
  const [comps, setComps] = useState<PayrollComponent[] | null>(null);
  const [picked, setPicked] = useState<
    { id: number; amount: number; note: string }[]
  >([]);
  const [pickOpen, setPickOpen] = useState(false);
  useEffect(() => {
    if (!canSalary) return;
    api.luong.components
      .list(token)
      .then((r) => setComps(r.items))
      .catch(() => setComps([]));
  }, [token, canSalary]);
  const [chuyenCan, setChuyenCan] = useState(0);
  // BH đóng ở nơi khác → công ty chỉ đóng TNLĐ-BNN (không trừ BHXH/BHYT/BHTN của NV).
  const [insuranceElsewhere, setInsuranceElsewhere] = useState(false);
  // Đoàn viên công đoàn → mới bị trừ đoàn phí công đoàn (mặc định không).
  const [unionMember, setUnionMember] = useState(false);
  // Chống tạo NV trùng nếu upload tệp lỗi sau khi hồ sơ đã được tạo.
  const [createdId, setCreatedId] = useState<number | null>(null);
  // Thâm niên đã có TRƯỚC khi vào làm — nhập theo NĂM (cho phép lẻ); submit lưu × 12 (tháng).
  const [priorSeniorityYears, setPriorSeniorityYears] = useState(0);

  function set<K extends keyof EmployeeInput>(k: K, v: EmployeeInput[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  const salaryBase = luongViTri + luongTrachNhiem;
  // Chỉ để XEM: tổng thâm niên = thâm niên trước khi vào + thời gian từ ngày vào tới nay.
  const seniorityText = seniorityLabel(priorSeniorityYears, form.hire_date);
  const gradeName =
    jg.grades?.find((g) => g.id === form.job_grade_id)?.name ?? null;

  async function submit() {
    setError(null);
    if (!form.full_name.trim()) {
      setStep(0);
      setError("Họ tên là bắt buộc.");
      return;
    }
    if (canSalary && luongViTri <= 0) {
      setStep(2);
      setError("Lương cơ bản (đóng BH) của nhân viên phải lớn hơn 0.");
      return;
    }
    setBusy(true);
    try {
      // Giữ id đã tạo để nếu lỗi giữa chừng, bấm Lưu lại KHÔNG tạo nhân viên trùng.
      let id = createdId;
      if (id == null) {
        const input: EmployeeInput = { ...form };
        input.prior_seniority_months = Math.round(priorSeniorityYears * 12);
        if (makeAccount && acc.username.trim()) {
          input.account = {
            username: acc.username.trim(),
            password: acc.password,
            role_id: acc.role_id === "" ? null : acc.role_id,
          };
        }
        if (canSalary) {
          input.initial_salary = {
            effective_from:
              form.hire_date || new Date().toISOString().slice(0, 10),
            luong_vi_tri: luongViTri,
            luong_trach_nhiem: luongTrachNhiem,
            luong_dot_1: luongDot1,
            chuyen_can: chuyenCan,
            insurance_elsewhere: insuranceElsewhere,
            union_member: unionMember,
            // Backend nhận PHÂN SỐ và chặn `le=1` ⇒ kẹp trần 100% ở đây, đừng để người gõ nhầm
            // "150" ăn nguyên cục 422 mà không hiểu vì sao.
            commission_pct: Math.min(commissionPct, 100) / 100,
          };
        }
        const res = await api.employees.create(token, input);
        id = res.employee.id;
        setCreatedId(id);
        // Gán khoản ngay sau khi có id — cùng nếp với upload file bên dưới.
        if (canSalary && picked.length) {
          await api.luong.components.setEmployeeValues(
            token,
            id,
            picked.map((p) => ({
              component_id: p.id,
              amount: p.amount,
              note: p.note.trim() || null,
            })),
          );
        }
      }
      // Upload các file đã chọn (cần id sau khi tạo).
      for (const f of files) {
        await api.employees.upload(token, id, f.file, f.doc_kind);
      }
      onCreated(id);
    } catch (e) {
      setError(errMsg(e));
      setBusy(false);
    }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box ns-modal__box--wide">
        <header className="ns-modal__head">
          <h2>Thêm nhân viên mới</h2>
          <button className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            ×
          </button>
        </header>

        <ol className="ns-steps">
          {STEPS.map((s, i) => (
            <li
              key={s}
              className={i === step ? "is-active" : i < step ? "is-done" : ""}
            >
              <span className="ns-steps__n">{i + 1}</span>
              {s}
            </li>
          ))}
        </ol>

        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}

          {STEPS[step] === "Định danh & việc làm" && (
            <div className="ns-grid">
              <Field label="Họ tên *">
                <input
                  value={form.full_name}
                  onChange={(e) => set("full_name", e.target.value)}
                />
              </Field>
              <Field label="Phòng/Tổ *">
                <select
                  value={form.department_id ?? ""}
                  onChange={(e) => {
                    const id =
                      e.target.value === "" ? null : Number(e.target.value);
                    // Đổi sang phòng KHÔNG phải sản xuất thì phải XOÁ bậc ngay: chỉ ẩn ô mà giữ
                    // state là vẫn submit bậc lên backend (backend không chặn) ⇒ kế toán nhận
                    // một nhân viên văn phòng mang bậc thợ.
                    setForm((f) => ({
                      ...f,
                      department_id: id,
                      job_grade_id: isProduction(meta, id)
                        ? f.job_grade_id
                        : null,
                    }));
                  }}
                >
                  {meta.departments.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Chức danh">
                <input
                  value={form.position ?? ""}
                  onChange={(e) => set("position", e.target.value)}
                />
              </Field>
              {isProduction(meta, form.department_id) && (
                <JobGradeField
                  grades={jg.grades}
                  err={jg.err}
                  reload={jg.reload}
                  addGrade={jg.addGrade}
                  value={form.job_grade_id ?? null}
                  onChange={(id) => set("job_grade_id", id)}
                  label="Bậc tay nghề"
                  // hint="Chỉ khai cho khối sản xuất. Khai bậc thôi — bậc KHÔNG làm đổi tiền lương."
                  canCreate={canCreateGrade}
                />
              )}
              <Field label="Thâm niên khi vào làm (năm)">
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  value={priorSeniorityYears || ""}
                  onChange={(e) =>
                    setPriorSeniorityYears(
                      e.target.value === "" ? 0 : Number(e.target.value),
                    )
                  }
                  placeholder="0"
                />
                {seniorityText && (
                  <span className="ns-field__hint">{seniorityText}</span>
                )}
              </Field>
              <Field label="Ngày vào">
                <input
                  type="date"
                  value={form.hire_date ?? ""}
                  onChange={(e) => set("hire_date", e.target.value)}
                />
              </Field>
              <Field label="Trạng thái">
                <select
                  value={form.status}
                  onChange={(e) => set("status", e.target.value)}
                >
                  <option value="probation">Thử việc</option>
                  <option value="active">Chính thức</option>
                </select>
              </Field>
              {form.status === "probation" && (
                <Field label="Ngày hết thử việc">
                  <input
                    type="date"
                    value={form.probation_end_date ?? ""}
                    onChange={(e) => set("probation_end_date", e.target.value)}
                  />
                </Field>
              )}
            </div>
          )}

          {STEPS[step] === "Cá nhân" && (
            <div className="ns-grid">
              <Field label="Ngày sinh">
                <input
                  type="date"
                  value={form.date_of_birth ?? ""}
                  onChange={(e) => set("date_of_birth", e.target.value)}
                />
              </Field>
              <Field label="Giới tính">
                <select
                  value={form.gender ?? ""}
                  onChange={(e) => set("gender", e.target.value || null)}
                >
                  <option value="">—</option>
                  <option value="male">Nam</option>
                  <option value="female">Nữ</option>
                  <option value="other">Khác</option>
                </select>
              </Field>
              <Field label="CCCD">
                <input
                  value={form.national_id ?? ""}
                  onChange={(e) => set("national_id", e.target.value)}
                />
              </Field>
              <Field label="SĐT">
                <input
                  value={form.phone ?? ""}
                  onChange={(e) => set("phone", e.target.value)}
                />
              </Field>
              <Field label="Email">
                <input
                  value={form.email ?? ""}
                  onChange={(e) => set("email", e.target.value)}
                />
              </Field>
              <Field label="Hộ khẩu">
                <input
                  value={form.permanent_address ?? ""}
                  onChange={(e) => set("permanent_address", e.target.value)}
                />
              </Field>
              <Field label="Chỗ ở hiện tại">
                <input
                  value={form.current_address ?? ""}
                  onChange={(e) => set("current_address", e.target.value)}
                />
              </Field>
              <Field label="Liên hệ khẩn (tên)">
                <input
                  value={form.emergency_contact_name ?? ""}
                  onChange={(e) =>
                    set("emergency_contact_name", e.target.value)
                  }
                />
              </Field>
              <Field label="Liên hệ khẩn (SĐT)">
                <input
                  value={form.emergency_contact_phone ?? ""}
                  onChange={(e) =>
                    set("emergency_contact_phone", e.target.value)
                  }
                />
              </Field>
              <Field label="Ghi chú">
                <input
                  value={form.note ?? ""}
                  onChange={(e) => set("note", e.target.value)}
                  placeholder="Ghi gì tuỳ ý…"
                />
              </Field>
            </div>
          )}

          {STEPS[step] === "Lương & BHXH" && (
            <div className="ns-grid">
              {canSalary ? (
                <>
                  <div className="ns-wizard__salary-intro ns-wizard__full">
                    <strong>Mức lương riêng của nhân viên</strong>
                    <span>
                      BHXH/BHYT/BHTN đóng trên lương cơ bản. Các khoản phụ cấp
                      là số cố định, cộng phẳng mỗi tháng.
                    </span>
                  </div>
                  <Field label="Lương cơ bản (đóng BH) *">
                    <input
                      type="number"
                      min={0}
                      step={100000}
                      value={luongViTri}
                      onChange={(e) => setLuongViTri(Number(e.target.value))}
                    />
                  </Field>
                  <Field label="Lương trách nhiệm">
                    <input
                      type="number"
                      min={0}
                      step={100000}
                      value={luongTrachNhiem}
                      onChange={(e) =>
                        setLuongTrachNhiem(Number(e.target.value))
                      }
                    />
                  </Field>
                  <div className="ns-wizard__salary-total ns-wizard__full">
                    <span>Mức nền theo hợp đồng</span>
                    <strong>{money(salaryBase)}</strong>
                  </div>
                  <Field label="Thưởng chuyên cần">
                    <input
                      type="number"
                      min={0}
                      step={50000}
                      value={chuyenCan}
                      onChange={(e) => setChuyenCan(Number(e.target.value))}
                    />
                  </Field>
                  <Field
                    label="Lương trả 1 lần (đợt 1)"
                    hint="Mức trả trong 1 lần. Điền sẵn khi lập phiếu 'lương đợt 1' ở màn Lương; duyệt xong mới trừ."
                  >
                    <input
                      type="number"
                      min={0}
                      step={100000}
                      value={luongDot1}
                      onChange={(e) => setLuongDot1(Number(e.target.value))}
                    />
                  </Field>
                  <Field
                    label="% hoa hồng (NV kinh doanh)"
                    hint="Bỏ trống / 0 nếu không phải nhân viên kinh doanh."
                  >
                    <input
                      type="number"
                      min={0}
                      max={100}
                      step={0.5}
                      value={commissionPct || ""}
                      onChange={(e) =>
                        setCommissionPct(
                          e.target.value === "" ? 0 : Number(e.target.value),
                        )
                      }
                      placeholder="0"
                    />
                  </Field>
                  {/* <div className="banner banner--warn ns-wizard__full">
                    Ô này <b>chỉ để KHAI</b> — hệ thống{" "}
                    <b>CHƯA tự cộng hoa hồng vào lương</b>. Muốn trả thì vẫn
                    phải thêm bằng tay ở <b>khoản thu nhập</b> của nhân viên
                    hoặc ngay trên phiếu lương.
                  </div> */}
                  <div className="ns-wizard__full">
                    <div className="ns-field__label">
                      Khoản thu nhập / phụ cấp
                    </div>
                    {picked.length === 0 && (
                      <p className="ns-wizard__hint">
                        Chưa chọn khoản nào. Chọn từ danh mục bên dưới — mỗi
                        khoản đã mang sẵn quy tắc chịu thuế TNCN hay không.
                      </p>
                    )}
                    {picked.map((p, i) => {
                      const c = comps?.find((x) => x.id === p.id);
                      return (
                        <div key={p.id} className="ns-comp-row">
                          <span className="ns-comp-row__name">
                            {c?.name ?? `#${p.id}`}
                            <span
                              className={
                                c?.is_taxable
                                  ? "ns-tag ns-tag--tax"
                                  : "ns-tag ns-tag--free"
                              }
                            >
                              {c?.is_taxable ? "Chịu thuế" : "Miễn thuế"}
                            </span>
                          </span>
                          <input
                            type="number"
                            min={0}
                            step={50000}
                            value={p.amount}
                            onChange={(e) =>
                              setPicked(
                                picked.map((x, j) =>
                                  j === i
                                    ? { ...x, amount: Number(e.target.value) }
                                    : x,
                                ),
                              )
                            }
                          />
                          <input
                            type="text"
                            placeholder="Ghi chú (không bắt buộc)"
                            value={p.note}
                            onChange={(e) =>
                              setPicked(
                                picked.map((x, j) =>
                                  j === i ? { ...x, note: e.target.value } : x,
                                ),
                              )
                            }
                          />
                          <button
                            type="button"
                            className="btn btn--ghost"
                            onClick={() =>
                              setPicked(picked.filter((_, j) => j !== i))
                            }
                          >
                            Gỡ
                          </button>
                        </div>
                      );
                    })}
                    <div className="ns-comp-add">
                      <button
                        type="button"
                        className="btn btn--ghost ns-comp-add__btn"
                        onClick={() => setPickOpen((v) => !v)}
                      >
                        + Thêm khoản thu nhập
                      </button>
                      {pickOpen && (
                        <>
                          <div
                            className="ns-comp-pop__veil"
                            onClick={() => setPickOpen(false)}
                          />
                          <div className="ns-comp-pop" role="listbox">
                            {(comps ?? []).filter(
                              (c) =>
                                c.is_active &&
                                !picked.some((p) => p.id === c.id),
                            ).length === 0 ? (
                              <p className="ns-comp-pop__empty">
                                Đã chọn hết khoản đang dùng.
                              </p>
                            ) : (
                              (comps ?? [])
                                .filter(
                                  (c) =>
                                    c.is_active &&
                                    !picked.some((p) => p.id === c.id),
                                )
                                .map((c) => (
                                  <button
                                    key={c.id}
                                    type="button"
                                    role="option"
                                    aria-selected={false}
                                    onClick={() => {
                                      setPicked([
                                        ...picked,
                                        { id: c.id, amount: 0, note: "" },
                                      ]);
                                      setPickOpen(false);
                                    }}
                                  >
                                    <span className="ns-comp-pop__name">
                                      {c.name}
                                    </span>
                                    <span
                                      className={
                                        c.is_taxable
                                          ? "ns-tag ns-tag--tax"
                                          : "ns-tag ns-tag--free"
                                      }
                                    >
                                      {c.is_taxable ? "Chịu thuế" : "Miễn thuế"}
                                    </span>
                                  </button>
                                ))
                            )}
                            <div className="ns-comp-pop__foot">
                              Không thấy khoản cần dùng? Tạo ở{" "}
                              <b>Cấu hình lương → Danh mục khoản thu nhập</b>.
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                  <label className="ns-check ns-wizard__full">
                    <input
                      type="checkbox"
                      checked={insuranceElsewhere}
                      onChange={(e) => setInsuranceElsewhere(e.target.checked)}
                    />
                    Bảo hiểm đóng ở nơi khác — công ty chỉ đóng TNLĐ-BNN (không
                    trừ BHXH/BHYT/BHTN của NV)
                  </label>
                  <label className="ns-check ns-wizard__full">
                    <input
                      type="checkbox"
                      checked={unionMember}
                      onChange={(e) => setUnionMember(e.target.checked)}
                    />
                    Đoàn viên công đoàn — có trừ đoàn phí công đoàn
                  </label>
                  {form.status === "probation" && salaryBase > 0 && (
                    <div className="ns-wizard__hint ns-wizard__hint--tv">
                      Thử việc: hệ thống tính 80% mức nền, dự kiến{" "}
                      {money(salaryBase * 0.8)} trước công và phụ cấp.
                    </div>
                  )}
                </>
              ) : (
                <div className="ns-wizard__hint">
                  Bạn không có quyền khai lương. Hồ sơ sẽ được tạo trước và
                  người có quyền Lương sẽ bổ sung mức sau.
                </div>
              )}
              <div className="ns-wizard__section-title ns-wizard__full">
                Bảo hiểm, thuế và tài khoản nhận lương
              </div>
              <Field label="Số sổ BHXH">
                <input
                  value={form.social_insurance_no ?? ""}
                  onChange={(e) => set("social_insurance_no", e.target.value)}
                />
              </Field>
              <Field label="MST cá nhân">
                <input
                  value={form.pit_tax_code ?? ""}
                  onChange={(e) => set("pit_tax_code", e.target.value)}
                />
              </Field>
              <Field label="Người phụ thuộc">
                <input
                  type="number"
                  min={0}
                  value={form.dependents_count ?? 0}
                  onChange={(e) =>
                    set("dependents_count", Number(e.target.value))
                  }
                />
              </Field>
              <Field label="Số tài khoản">
                <input
                  value={form.bank_account ?? ""}
                  onChange={(e) => set("bank_account", e.target.value)}
                />
              </Field>
              <Field label="Ngân hàng">
                <input
                  value={form.bank_name ?? ""}
                  onChange={(e) => set("bank_name", e.target.value)}
                />
              </Field>
            </div>
          )}

          {STEPS[step] === "Đính kèm" && (
            <div>
              <FilePicker
                onAdd={(file, kind) =>
                  setFiles((fs) => [...fs, { file, doc_kind: kind }])
                }
              />
              <ul className="ns-filelist-v2">
                {files.map((f, i) => {
                  const typeInfo = getFileTypeInfo(f.file.name);
                  const IconComponent = typeInfo.icon;
                  return (
                    <li key={i} className="ns-fileitem">
                      <div className={`ns-fileitem__icon ${typeInfo.className}`}>
                        <IconComponent size={18} />
                      </div>
                      <div className="ns-fileitem__main">
                        <div className="ns-fileitem__name-group">
                          <span className="ns-fileitem__name" title={f.file.name}>
                            {f.file.name}
                          </span>
                          <div className="ns-fileitem__sub">
                            {formatFileSize(f.file.size)}
                          </div>
                        </div>
                        <span className="ns-fileitem__badge">
                          {DOC_KIND_LABEL[f.doc_kind] ?? f.doc_kind}
                        </span>
                      </div>
                      <div className="ns-fileitem__actions">
                        <button
                          type="button"
                          className="btn btn--ghost ns-danger btn--sm"
                          style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
                          title="Xóa tệp"
                          onClick={() => setFiles((fs) => fs.filter((_, j) => j !== i))}
                        >
                          <Trash2 size={13} /> Bỏ
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {STEPS[step] === "Tài khoản" && (
            <div>
              <label className="ns-check">
                <input
                  type="checkbox"
                  checked={makeAccount}
                  onChange={(e) => setMakeAccount(e.target.checked)}
                />
                Tạo tài khoản đăng nhập cho nhân viên này
              </label>
              {makeAccount && (
                <div className="ns-grid" style={{ marginTop: 12 }}>
                  <Field label="Tên đăng nhập *">
                    <input
                      value={acc.username}
                      onChange={(e) =>
                        setAcc({ ...acc, username: e.target.value })
                      }
                    />
                  </Field>
                  <Field label="Mật khẩu tạm *">
                    <input
                      type="text"
                      value={acc.password}
                      onChange={(e) =>
                        setAcc({ ...acc, password: e.target.value })
                      }
                    />
                  </Field>
                  {/* Không có vai trò thì NV đăng nhập được nhưng không thấy gì — phải chọn ngay
                      tại đây, đừng bắt sang màn khác gán. Vai trò thuộc phòng của hồ sơ. */}
                  <Field label="Vai trò">
                    <select
                      value={acc.role_id}
                      onChange={(e) =>
                        setAcc({
                          ...acc,
                          role_id: e.target.value ? Number(e.target.value) : "",
                        })
                      }
                    >
                      <option value="">
                        — chưa gán (đăng nhập nhưng chưa thấy gì) —
                      </option>
                      {meta.roles
                        .filter((r) => r.department_id === form.department_id)
                        .map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.name}
                          </option>
                        ))}
                    </select>
                  </Field>
                </div>
              )}
              <div className="ns-review">
                <h4>Xem lại</h4>
                <p>
                  <strong>{form.full_name || "(chưa nhập tên)"}</strong> ·{" "}
                  {meta.departments.find((d) => d.id === form.department_id)
                    ?.name ?? "—"}{" "}
                  · {form.status === "active" ? "Chính thức" : "Thử việc"}
                  {gradeName ? ` · ${gradeName}` : ""}
                </p>
                {canSalary && (
                  <p>
                    Lương cơ bản <strong>{money(salaryBase)}</strong>
                  </p>
                )}
                {canSalary && commissionPct > 0 && (
                  <p>Hoa hồng {commissionPct}% (chỉ khai)</p>
                )}
                <p>
                  Ngày vào {fmtDate(form.hire_date)} · {files.length} tệp đính
                  kèm
                  {makeAccount && acc.username
                    ? ` · tài khoản "${acc.username}"${acc.role_id ? ` (${meta.roles.find((r) => r.id === acc.role_id)?.name})` : " — CHƯA gán vai trò"}`
                    : ""}
                </p>
              </div>
            </div>
          )}
        </div>

        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <div className="ns-modal__footright">
            {step > 0 && (
              <button
                className="btn btn--ghost"
                onClick={() => setStep((s) => s - 1)}
                disabled={busy}
              >
                ‹ Trước
              </button>
            )}
            {/* Nút ĐI TỚI của wizard = hành động chính của hộp thoại → cam (`accent`).
                "Tiếp" và "Lưu" không bao giờ hiện cùng lúc nên vẫn đúng luật MỘT nút cam. */}
            {step < STEPS.length - 1 && (
              <Button variant="accent" onClick={() => setStep((s) => s + 1)}>
                Tiếp ›
              </Button>
            )}
            {step === STEPS.length - 1 && (
              <Button variant="accent" onClick={submit} loading={busy}>
                {busy ? "Đang lưu…" : "Lưu & xem hồ sơ"}
              </Button>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}

function getFileTypeInfo(fileName: string) {
  const ext = fileName.split(".").pop()?.toLowerCase();
  if (ext === "pdf") {
    return { icon: FileText, className: "ns-fileitem__icon--pdf" };
  }
  if (["png", "jpg", "jpeg", "webp", "gif", "svg"].includes(ext || "")) {
    return { icon: Image, className: "ns-fileitem__icon--img" };
  }
  return { icon: File, className: "ns-fileitem__icon--doc" };
}

function formatFileSize(bytes?: number): string | null {
  if (!bytes) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function FilePicker({
  onAdd,
  disabled = false,
  compact = false,
  defaultKind = "hop_dong",
}: {
  onAdd: (file: File, kind: string) => void;
  disabled?: boolean;
  compact?: boolean;
  defaultKind?: string;
}) {
  const [kind, setKind] = useState(defaultKind || "hop_dong");
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (defaultKind && defaultKind !== "all") {
      setKind(defaultKind);
    }
  }, [defaultKind]);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!disabled && !isDragging) setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (disabled) return;
    const f = e.dataTransfer.files?.[0];
    if (f) onAdd(f, kind);
  };

  if (compact) {
    return (
      <div
        className={`ns-upload-bar ${isDragging ? "ns-upload-bar--dragging" : ""}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          style={{ display: "none" }}
          disabled={disabled}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onAdd(f, kind);
            e.target.value = "";
          }}
        />
        <div className="ns-upload-bar__left">
          <Button
            variant="accent"
            className="btn--sm"
            disabled={disabled}
            onClick={() => inputRef.current?.click()}
          >
            <UploadCloud size={15} style={{ marginRight: 4 }} />
            Tải tệp đính kèm
          </Button>
          <select
            className="ns-dropzone__select"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            disabled={disabled}
          >
            {Object.entries(DOC_KIND_LABEL).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
          <span className="ns-upload-bar__drop-text">
            hoặc kéo & thả tệp trực tiếp vào đây
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`ns-dropzone--empty ${isDragging ? "ns-dropzone--dragging" : ""}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <input
        ref={inputRef}
        type="file"
        style={{ display: "none" }}
        disabled={disabled}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onAdd(f, kind);
          e.target.value = "";
        }}
      />
      <div
        className="ns-dropzone__body"
        onClick={() => !disabled && inputRef.current?.click()}
      >
        <div className="ns-dropzone__icon-wrap">
          <UploadCloud size={20} />
        </div>
        <p className="ns-dropzone__prompt">
          Kéo & thả tệp vào đây hoặc{" "}
          <button type="button" className="ns-dropzone__btn" disabled={disabled}>
            chọn tệp từ máy tính
          </button>
        </p>
        <p className="ns-dropzone__hint">
          Hợp đồng, CCCD, bằng cấp (PDF, Word, Ảnh)... tải lên để lưu hồ sơ
        </p>
        <div
          style={{ marginTop: 6 }}
          onClick={(e) => e.stopPropagation()}
        >
          <select
            className="ns-dropzone__select"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            disabled={disabled}
          >
            {Object.entries(DOC_KIND_LABEL).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}

/** "Thâm niên hiện tại: X năm Y tháng" (chỉ để xem) = thâm niên khai trước khi vào (đổi ra
 *  tháng) + số tháng từ ngày vào tới nay. Trả null khi chưa có gì để hiện. */
function seniorityLabel(
  priorYears: number,
  hireDate?: string | null,
): string | null {
  const prior = Math.round((priorYears || 0) * 12);
  let fromHire = 0;
  if (hireDate) {
    const h = new Date(hireDate);
    if (!Number.isNaN(h.getTime())) {
      const now = new Date();
      fromHire = Math.max(
        0,
        (now.getFullYear() - h.getFullYear()) * 12 +
          (now.getMonth() - h.getMonth()),
      );
    }
  }
  const total = prior + fromHire;
  if (total <= 0) return null;
  return `Thâm niên hiện tại: ${Math.floor(total / 12)} năm ${total % 12} tháng`;
}

function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  const required = label.trimEnd().endsWith("*");
  const text = required ? label.trimEnd().slice(0, -1).trimEnd() : label;
  return (
    <label className="ns-field">
      <span className="ns-field__label">
        {text}
        {required && (
          <span className="ns-field__required" aria-hidden="true">
            {" "}
            *
          </span>
        )}
      </span>
      {children}
      {hint && <span className="ns-field__hint">{hint}</span>}
    </label>
  );
}

type Tab = "info" | "salary" | "account" | "events" | "files" | "activity";

function EmployeeDetailPanel({
  token,
  employeeId,
  meta,
  navigate,
  onClose,
  onChanged,
}: {
  token: string;
  employeeId: number;
  meta: EmployeeMeta | null;
  navigate?: NavigateFn;
  onClose: () => void;
  onChanged: () => void;
}) {
  const can = useCan();
  const canUpdate = can("nhan_su", "update");
  const canEditSalaryFields = can("nhan_su", "edit_salary");
  const canViewSalary =
    can("nhan_su", "view_salary") || canEditSalaryFields;
  const canManageStatus = can("nhan_su", "manage_status");
  const canTransfer = can("nhan_su", "transfer");
  const canViewAccount = can("nguoi_dung", "read");
  const [emp, setEmp] = useState<EmployeeDetail | null>(null);
  const [tab, setTab] = useState<Tab>("info");
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<string | null>(null); // dialog kind
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [editInfo, setEditInfo] = useState(false);
  const [editSalary, setEditSalary] = useState(false);

  const reload = useCallback(() => {
    api.employees
      .get(token, employeeId)
      .then(setEmp)
      .catch((e) => setError(errMsg(e)));
  }, [token, employeeId]);

  useEffect(() => {
    setTab("info");
    setEditInfo(false);
    setEditSalary(false);
    reload();
  }, [reload]);

  if (!emp) {
    // Tách "đang tải" khỏi "gọi hỏng": trước đây cả hai in cùng một dòng chữ xám nên mất
    // mạng cũng trông y như đang chờ — người dùng ngồi đợi mãi một khay không bao giờ mở.
    return (
      <div className="ns2-detail__loading">
        {error ? (
          <EmptyState trangThai="loi" loi={error} onThuLai={reload} />
        ) : (
          <EmptyState trangThai="dang-tai" />
        )}
      </div>
    );
  }

  const resigned = emp.status === "resigned";
  const tabs: [Tab, string][] = [
    ["info", "Thông tin"],
    ...(canViewSalary ? [["salary", "Lương & BHXH"] as [Tab, string]] : []),
    // Gộp từ màn Người dùng (đã bỏ): mọi tài khoản thuộc một hồ sơ nên quản ngay tại đây.
    ...(canViewAccount
      ? [["account", "Tài khoản & Quyền"] as [Tab, string]]
      : []),
    ["events", "Quá trình công tác"],
    ["files", "Đính kèm"],
    ["activity", "Nhật ký"],
  ];

  return (
    <div className="ns2-detail">
      <header className="ns2-detail__head">
        <button
          type="button"
          className="ns-modal__close-btn"
          onClick={onClose}
          aria-label="Đóng"
        >
          <X size={18} />
        </button>
        <div className="ns-avatar ns-avatar--lg">
          {assetUrl(emp.photo_url) ? (
            <img src={assetUrl(emp.photo_url)!} alt={emp.full_name} />
          ) : (
            emp.full_name.trim().slice(0, 1).toUpperCase()
          )}
        </div>
        <div className="ns2-detail__id">
          <h2>
            {emp.full_name}
            <StatusBadge status={emp.status} />
          </h2>
          <p className="ns-detail__meta">
            <Briefcase size={13} />
            {/* Tên bậc đã tự mang chữ "Bậc" (Bậc 1…Bậc 5) → thêm tiền tố nữa ra "Bậc Bậc 1". */}
            {emp.code} · {emp.department_name ?? "—"} · {emp.position ?? "—"}
            {(emp.job_grade_name ?? emp.job_grade)
              ? ` · ${emp.job_grade_name ?? emp.job_grade}`
              : ""}
          </p>
          <p className="ns-detail__meta">
            <Calendar size={13} />
            Vào làm {fmtDate(emp.hire_date)} ·{" "}
            {emp.account_username
              ? `🔑 ${emp.account_username}`
              : "chưa nối tài khoản"}
          </p>
        </div>
      </header>

      {(navigate || canUpdate || canManageStatus || canTransfer) && (
        <div className="ns-detail__actions">
          <div className="ns-detail__shortcuts">
            {navigate && (
              <>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() =>
                    navigate("cham-cong", { focusEmployeeId: emp.id })
                  }
                >
                  <Clock size={12} />
                  Chấm công
                </button>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() =>
                    navigate("nghi-phep", { focusEmployeeId: emp.id })
                  }
                >
                  <Calendar size={12} />
                  Nghỉ phép
                </button>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() => navigate("luong", { focusEmployeeId: emp.id })}
                >
                  <CreditCard size={12} />
                  Lương
                </button>
              </>
            )}
          </div>
          <div className="ns-detail__ops">
            {canUpdate && tab === "info" && !resigned && (
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => setEditInfo(!editInfo)}
              >
                <Edit2 size={12} />
                {editInfo ? "Hủy sửa" : "Sửa thông tin"}
              </button>
            )}
            {canUpdate &&
              canEditSalaryFields &&
              tab === "salary" &&
              canViewSalary &&
              !resigned && (
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => setEditSalary(!editSalary)}
              >
                <Edit2 size={12} />
                {editSalary ? "Hủy sửa" : "Sửa lương & BHXH"}
              </button>
            )}
            {(canManageStatus || canTransfer) && (
              <div className="ns-dropdown">
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() => setDropdownOpen(!dropdownOpen)}
                >
                  Thao tác hồ sơ
                  <ChevronDown size={12} />
                </button>
                {dropdownOpen && (
                  <div className="ns-dropdown-menu">
                    {canManageStatus && emp.status === "probation" && (
                      <button
                        type="button"
                        className="ns-dropdown-item"
                        onClick={() => {
                          setAction("confirm");
                          setDropdownOpen(false);
                        }}
                      >
                        <UserCheck size={14} /> Chuyển chính thức
                      </button>
                    )}
                    {canManageStatus && emp.status === "active" && (
                      <button
                        type="button"
                        className="ns-dropdown-item"
                        onClick={() => {
                          setAction("leave_start");
                          setDropdownOpen(false);
                        }}
                      >
                        <UserMinus size={14} /> Cho nghỉ dài hạn
                      </button>
                    )}
                    {canManageStatus && emp.status === "on_leave" && (
                      <button
                        type="button"
                        className="ns-dropdown-item"
                        onClick={() => {
                          setAction("leave_end");
                          setDropdownOpen(false);
                        }}
                      >
                        <UserCheck size={14} /> Đi làm lại
                      </button>
                    )}
                    {canTransfer && !resigned && (
                      <button
                        type="button"
                        className="ns-dropdown-item"
                        onClick={() => {
                          setAction("transfer");
                          setDropdownOpen(false);
                        }}
                      >
                        <TrendingUp size={14} /> Điều chuyển tổ
                      </button>
                    )}
                    {canTransfer && !resigned && (
                      <button
                        type="button"
                        className="ns-dropdown-item"
                        onClick={() => {
                          setAction("promote");
                          setDropdownOpen(false);
                        }}
                      >
                        <TrendingUp size={14} /> Nâng bậc / Chức danh
                      </button>
                    )}
                    {canManageStatus && !resigned && (
                      <button
                        type="button"
                        className="ns-dropdown-item"
                        onClick={() => {
                          setAction("suspend");
                          setDropdownOpen(false);
                        }}
                      >
                        <AlertTriangle size={14} /> Đình chỉ công tác
                      </button>
                    )}
                    {canManageStatus && !resigned && (
                      <button
                        type="button"
                        className="ns-dropdown-item ns-danger"
                        onClick={() => {
                          setAction("resign");
                          setDropdownOpen(false);
                        }}
                      >
                        <UserMinus size={14} /> Thôi việc / Nghỉ việc
                      </button>
                    )}
                    {canManageStatus && resigned && (
                      <button
                        type="button"
                        className="ns-dropdown-item"
                        onClick={() => {
                          setAction("reinstate");
                          setDropdownOpen(false);
                        }}
                      >
                        <UserPlus size={14} /> Tuyển dụng lại
                      </button>
                    )}
                    {/* Tài khoản đăng nhập quản ở tab "Tài khoản & Quyền" — mọi tài khoản
                        thuộc một hồ sơ nên không còn "gỡ liên kết". */}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      <nav className="ns-tabs ns2-detail__tabs">
        {tabs.map(([id, label]) => (
          <button
            key={id}
            className={tab === id ? "is-active" : ""}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="ns2-detail__body">
        {tab === "info" && (
          <InfoTab
            token={token}
            emp={emp}
            meta={meta}
            canUpdate={canUpdate}
            edit={editInfo}
            setEdit={setEditInfo}
            onSaved={() => {
              reload();
              onChanged();
            }}
          />
        )}
        {tab === "salary" && canViewSalary && (
          <SalaryTab
            token={token}
            emp={emp}
            edit={editSalary}
            setEdit={setEditSalary}
            onSaved={() => {
              reload();
              onChanged();
            }}
          />
        )}
        {tab === "account" && canViewAccount && (
          <AccountTab
            token={token}
            emp={emp}
            meta={meta}
            onChanged={() => {
              reload();
              onChanged();
            }}
          />
        )}
        {tab === "events" && (
          <EventsTab token={token} employeeId={employeeId} meta={meta} />
        )}
        {tab === "files" && (
          <FilesTab
            token={token}
            employeeId={employeeId}
            canUpdate={canUpdate}
          />
        )}
        {tab === "activity" && (
          <ActivityTab token={token} employeeId={employeeId} />
        )}
      </div>

      {action && (
        <ActionDialog
          token={token}
          emp={emp}
          meta={meta}
          kind={action}
          onClose={() => setAction(null)}
          onDone={() => {
            setAction(null);
            reload();
            onChanged();
          }}
        />
      )}
    </div>
  );
}

function InfoTab({
  token,
  emp,
  meta,
  canUpdate,
  edit,
  setEdit,
  onSaved,
}: {
  token: string;
  emp: EmployeeDetail;
  meta: EmployeeMeta | null;
  canUpdate: boolean;
  edit: boolean;
  setEdit: (e: boolean) => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<EmployeeInput>({
    ...emp,
  } as unknown as EmployeeInput);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shifts, setShifts] = useState<WorkShift[]>([]);
  useEffect(() => {
    api.attendance
      .shifts(token)
      .then((r) => setShifts(r.items))
      .catch(() => setShifts([]));
  }, [token]);
  const shiftName =
    shifts.find((s) => s.id === emp.default_shift_id)?.name ?? null;
  const resigned = emp.status === "resigned";

  function set<K extends keyof EmployeeInput>(k: K, v: EmployeeInput[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }
  async function save() {
    setBusy(true);
    setError(null);
    try {
      // Ca làm việc KHÔNG gán ở đây nữa (Chấm công → Khai ca → Phân ca tháng là nơi duy
      // nhất). Bỏ khỏi payload để form hồ sơ không bao giờ ghi đè ca — đường ghi này
      // không tạo mốc hiệu lực nên sẽ làm mất dấu lịch sử đổi ca.
      const { default_shift_id: _ignored, ...payload } = form;
      await api.employees.update(token, emp.id, payload as EmployeeInput);
      setEdit(false);
      onSaved();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  if (edit) {
    return (
      <div>
        {error && <div className="banner banner--error">{error}</div>}
        <div className="ns-grid">
          <Field label="Họ tên *">
            <input
              value={form.full_name}
              onChange={(e) => set("full_name", e.target.value)}
            />
          </Field>
          <Field label="Chức danh">
            <input
              value={form.position ?? ""}
              onChange={(e) => set("position", e.target.value)}
            />
          </Field>
          <Field label="SĐT">
            <input
              value={form.phone ?? ""}
              onChange={(e) => set("phone", e.target.value)}
            />
          </Field>
          <Field label="Email">
            <input
              value={form.email ?? ""}
              onChange={(e) => set("email", e.target.value)}
            />
          </Field>
          <Field label="CCCD">
            <input
              value={form.national_id ?? ""}
              onChange={(e) => set("national_id", e.target.value)}
            />
          </Field>
          <Field label="Ngày cấp CCCD">
            <input
              type="date"
              value={form.national_id_date ?? ""}
              onChange={(e) => set("national_id_date", e.target.value)}
            />
          </Field>
          <Field label="Nơi cấp CCCD">
            <input
              value={form.national_id_place ?? ""}
              onChange={(e) => set("national_id_place", e.target.value)}
            />
          </Field>
          <Field label="Hộ khẩu">
            <input
              value={form.permanent_address ?? ""}
              onChange={(e) => set("permanent_address", e.target.value)}
            />
          </Field>
          <Field label="Chỗ ở hiện tại">
            <input
              value={form.current_address ?? ""}
              onChange={(e) => set("current_address", e.target.value)}
            />
          </Field>
          <Field label="Liên hệ khẩn (tên)">
            <input
              value={form.emergency_contact_name ?? ""}
              onChange={(e) => set("emergency_contact_name", e.target.value)}
            />
          </Field>
          <Field label="Liên hệ khẩn (SĐT)">
            <input
              value={form.emergency_contact_phone ?? ""}
              onChange={(e) => set("emergency_contact_phone", e.target.value)}
            />
          </Field>
          <Field label="Ghi chú">
            <input
              value={form.note ?? ""}
              onChange={(e) => set("note", e.target.value)}
            />
          </Field>
        </div>
        <div className="ns2-editfoot">
          <button
            className="btn btn--ghost"
            onClick={() => setEdit(false)}
            disabled={busy}
          >
            Hủy
          </button>
          {/* Hành động chính của form đang mở → cam. Mỗi tab chỉ có ĐÚNG một nút Lưu nên
              khay hồ sơ không bao giờ hiện hai nút cam cùng lúc. */}
          <Button variant="accent" onClick={save} loading={busy}>
            {busy ? "Đang lưu…" : "Lưu"}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="ns-info-sections">
        <InfoCard title="Định danh & việc làm" icon={Briefcase}>
          <InfoField label="Mã NV" value={emp.code} icon={Briefcase} />
          <InfoField
            label="Phòng/Tổ"
            value={emp.department_name}
            icon={Users}
          />
          <InfoField label="Chức danh" value={emp.position} icon={UserCheck} />
          {/* NƠI DUY NHẤT hiện bậc trong hồ sơ. Bậc không dính tiền nên không thuộc tab Lương,
              và chỉ đổi được qua Thao tác hồ sơ (đường ghi thẳng đã bị backend bỏ qua). */}
          {(isProduction(meta, emp.department_id) ||
            (emp.job_grade_name ?? emp.job_grade)) && (
            <InfoField
              label="Bậc tay nghề"
              value={emp.job_grade_name ?? emp.job_grade}
              icon={TrendingUp}
              hint={
                canUpdate && !resigned
                  ? "Đổi bậc ở Thao tác hồ sơ → Nâng bậc / Chức danh."
                  : undefined
              }
            />
          )}
          <InfoField
            label="Ngày vào"
            value={fmtDate(emp.hire_date)}
            icon={Calendar}
          />
          <InfoField
            label="Hết thử việc"
            value={fmtDate(emp.probation_end_date)}
            icon={Calendar}
          />
          <InfoField
            label="Ca làm việc"
            value={shiftName ?? "— chưa gán —"}
            icon={Clock}
            hint="Gán/đổi ca ở Chấm công → Khai ca → Phân ca tháng"
          />
          {emp.resign_date && (
            <InfoField
              label="Ngày nghỉ"
              value={fmtDate(emp.resign_date)}
              icon={Calendar}
            />
          )}
          {emp.resign_reason && (
            <InfoField
              label="Lý do nghỉ"
              value={emp.resign_reason}
              icon={FileText}
            />
          )}
        </InfoCard>
        <InfoCard title="Cá nhân" icon={Users}>
          <InfoField
            label="Ngày sinh"
            value={fmtDate(emp.date_of_birth)}
            icon={Calendar}
          />
          <InfoField
            label="Giới tính"
            value={emp.gender ? GENDER_LABEL[emp.gender] : null}
            icon={Users}
          />
          <InfoField label="CCCD" value={emp.national_id} icon={FileText} />
          <InfoField
            label="Ngày cấp"
            value={fmtDate(emp.national_id_date)}
            icon={Calendar}
          />
          <InfoField
            label="Nơi cấp"
            value={emp.national_id_place}
            icon={MapPin}
          />
          <InfoField label="SĐT" value={emp.phone} icon={Phone} />
          <InfoField label="Email" value={emp.email} icon={Mail} />
          <InfoField
            label="Hộ khẩu"
            value={emp.permanent_address}
            icon={MapPin}
          />
          <InfoField label="Chỗ ở" value={emp.current_address} icon={MapPin} />
          <InfoField
            label="Liên hệ khẩn"
            value={
              emp.emergency_contact_name
                ? `${emp.emergency_contact_name} · ${emp.emergency_contact_phone ?? ""}`
                : null
            }
            icon={Phone}
          />
        </InfoCard>
      </div>
      <InfoCard title="Khác" icon={FileText}>
        <InfoField label="Ghi chú" value={emp.note} icon={FileText} />
      </InfoCard>
    </div>
  );
}

// Tab Lương & BHXH — dữ liệu nhạy cảm (chỉ hiện với quyền `nhan_su:view_salary`).
// "Nhóm lương / Bậc lương" (`payroll_group` / `pay_grade_key`) VẪN ĐỂ NGOÀI MÀN: PRD v2 bỏ hẳn
// "mức mặc định theo nhóm" nên nhóm lương không còn trục dùng nào, engine cũng không đọc — để
// lại chỉ khiến người dùng tưởng chọn nhóm là đã gán lương (PRD Cấu hình lương §8, bệnh B3).
// Khoản thu nhập gán theo TỪNG NGƯỜI: Lương → Lương nhân viên → Sửa lương → "+ Thêm khoản thu
// nhập" (CHỌN từ danh mục — màn nhân sự không có đường tạo khoản mới).
// Cách tính thuế TNCN (`pit_mode`) chỉ HIỆN ở đây, sửa ở Lương → Lương nhân viên → Sửa lương
// (một nơi khai, tránh 2 chỗ cùng sửa một số).
function SalaryTab({
  token,
  emp,
  edit,
  setEdit,
  onSaved,
}: {
  token: string;
  emp: EmployeeDetail;
  edit: boolean;
  setEdit: (e: boolean) => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<EmployeeInput>({
    ...emp,
  } as unknown as EmployeeInput);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  function set<K extends keyof EmployeeInput>(k: K, v: EmployeeInput[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }
  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.employees.update(token, emp.id, form);
      setEdit(false);
      onSaved();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  if (edit) {
    return (
      <div>
        {error && <div className="banner banner--error">{error}</div>}
        {/* Không còn ô "Bậc thợ" ở đây: `PUT /api/employees/{id}` CỐ TÌNH bỏ qua bậc (đổi bậc
            phải sinh mốc quá trình công tác) ⇒ ô sửa ở đây là đường ghi CHẾT, gõ xong bấm Lưu
            vẫn không đổi gì. Bậc xem ở tab Thông tin, đổi ở Thao tác hồ sơ → Nâng bậc. */}
        <div className="ns-grid">
          <Field label="Số sổ BHXH">
            <input
              value={form.social_insurance_no ?? ""}
              onChange={(e) => set("social_insurance_no", e.target.value)}
            />
          </Field>
          <Field label="MST cá nhân">
            <input
              value={form.pit_tax_code ?? ""}
              onChange={(e) => set("pit_tax_code", e.target.value)}
            />
          </Field>
          <Field
            label="Người phụ thuộc"
            hint="Mỗi người phụ thuộc được giảm trừ thêm khi tính thuế TNCN (mức lấy ở Cấu hình lương)."
          >
            <input
              type="number"
              min={0}
              value={form.dependents_count ?? 0}
              onChange={(e) => set("dependents_count", Number(e.target.value))}
            />
          </Field>
          <Field label="Số tài khoản">
            <input
              value={form.bank_account ?? ""}
              onChange={(e) => set("bank_account", e.target.value)}
            />
          </Field>
          <Field label="Ngân hàng">
            <input
              value={form.bank_name ?? ""}
              onChange={(e) => set("bank_name", e.target.value)}
            />
          </Field>
        </div>
        <div className="ns2-editfoot">
          <button
            className="btn btn--ghost"
            onClick={() => setEdit(false)}
            disabled={busy}
          >
            Hủy
          </button>
          {/* Hành động chính của form đang mở → cam. Mỗi tab chỉ có ĐÚNG một nút Lưu nên
              khay hồ sơ không bao giờ hiện hai nút cam cùng lúc. */}
          <Button variant="accent" onClick={save} loading={busy}>
            {busy ? "Đang lưu…" : "Lưu"}
          </Button>
        </div>
      </div>
    );
  }
  return (
    <div>
      <div className="ns-info-sections">
        <CommissionCard token={token} employeeId={emp.id} />
        <InfoCard title="BHXH / TNCN" icon={FileText}>
          <InfoField
            label="Số sổ BHXH"
            value={emp.social_insurance_no}
            icon={FileText}
          />
          <InfoField
            label="MST cá nhân"
            value={emp.pit_tax_code}
            icon={FileText}
          />
          <InfoField
            label="Người phụ thuộc"
            value={String(emp.dependents_count)}
            icon={Users}
          />
          <InfoField
            label="Cách tính thuế TNCN"
            value={emp.pit_mode ? PIT_MODE_META[emp.pit_mode].label : null}
            icon={FileText}
            hint="Đổi ở Lương → Lương nhân viên → Sửa lương."
          />
        </InfoCard>
      </div>
      <InfoCard title="Ngân hàng" icon={Lock}>
        <InfoField
          label="Tài khoản NH"
          value={
            emp.bank_account
              ? `${emp.bank_account} · ${emp.bank_name ?? ""}`
              : null
          }
          icon={CreditCard}
        />
      </InfoCard>
    </div>
  );
}

/** % hoa hồng của NV kinh doanh — CHỈ ĐỌC ở đây, sửa ở Lương → Lương nhân viên → Sửa lương.
 *  Không cho sửa tại drawer vì `POST /api/luong/salaries/{id}` luôn đẻ một mốc lương MỚI với
 *  TOÀN BỘ các số; drawer không giữ `luong_vi_tri`/phụ cấp nên post từ đây là lương về 0. */
function CommissionCard({
  token,
  employeeId,
}: {
  token: string;
  employeeId: number;
}) {
  const [state, setState] = useState<
    | { kind: "loading" }
    | { kind: "forbidden" }
    | { kind: "ok"; pct: number | null }
    | { kind: "error" }
  >({ kind: "loading" });

  useEffect(() => {
    let alive = true;
    setState({ kind: "loading" });
    api.luong
      .salaries(token, employeeId)
      .then((r) => {
        if (!alive) return;
        const latest = r.items.length
          ? [...r.items].sort((a, b) =>
              b.effective_from.localeCompare(a.effective_from),
            )[0]
          : null;
        const pct = latest?.commission_pct ? latest.commission_pct * 100 : null;
        setState({ kind: "ok", pct });
      })
      .catch((e) => {
        if (!alive) return;
        // 403 ⇒ ẨN HẲN thẻ. Hiện "—" là NÓI DỐI: "—" nghĩa là chưa khai, còn ở đây là mình
        // không được phép biết — người xem sẽ kết luận nhầm là NV không có hoa hồng.
        if (e instanceof ApiError && e.status === 403)
          setState({ kind: "forbidden" });
        else setState({ kind: "error" });
      });
    return () => {
      alive = false;
    };
  }, [token, employeeId]);

  if (state.kind === "loading" || state.kind === "forbidden") return null;
  const pct = state.kind === "ok" ? state.pct : null;
  return (
    <InfoCard title="Hoa hồng kinh doanh" icon={TrendingUp}>
      <InfoField
        label="% hoa hồng"
        value={pct != null ? `${pct}%` : null}
        icon={TrendingUp}
        hint={
          "Chỉ để khai — hệ thống chưa tự cộng vào lương. Đổi ở Lương → Lương nhân viên → Sửa lương." +
          (state.kind === "error" ? " Không đọc được số hoa hồng." : "")
        }
      />
    </InfoCard>
  );
}

/** Mật khẩu tạm dễ đọc (bỏ 0/O/1/l/I để khỏi đọc nhầm khi bàn giao). */
function genPassword(len = 12): string {
  const chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789";
  const buf = new Uint32Array(len);
  crypto.getRandomValues(buf);
  return Array.from(buf, (n) => chars[n % chars.length]).join("");
}

function deviceLabel(ua: string | null): string {
  if (!ua) return "Thiết bị không rõ";
  const browser = /Edg\//.test(ua)
    ? "Edge"
    : /Chrome\//.test(ua)
      ? "Chrome"
      : /Safari\//.test(ua)
        ? "Safari"
        : /Firefox\//.test(ua)
          ? "Firefox"
          : "Trình duyệt khác";
  const os = /Windows/.test(ua)
    ? "Windows"
    : /Mac OS/.test(ua)
      ? "macOS"
      : /Android/.test(ua)
        ? "Android"
        : /iPhone|iPad/.test(ua)
          ? "iOS"
          : "Hệ khác";
  return `${browser} · ${os}`;
}

/** Tab "Tài khoản & Quyền" — gộp từ màn Người dùng cũ (đã bỏ). Mọi tài khoản đều thuộc một
 * hồ sơ, nên đây là nơi DUY NHẤT cấp/quản tài khoản đăng nhập của nhân viên. */
function AccountTab({
  token,
  emp,
  meta,
  onChanged,
}: {
  token: string;
  emp: EmployeeDetail;
  meta: EmployeeMeta | null;
  onChanged: () => void;
}) {
  const can = useCan();
  const canCreate = can("nhan_su", "update");
  const canAssignRole = can("nguoi_dung", "assign_role");
  const canReset = can("nguoi_dung", "reset_password");
  const canLock = can("nguoi_dung", "lock");
  const canRevoke = can("nguoi_dung", "revoke_sessions");

  const [row, setRow] = useState<UserRow | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activity, setActivity] = useState<AuditRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tempPw, setTempPw] = useState<string | null>(null);
  // form tạo tài khoản (khi hồ sơ chưa có)
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState(() => genPassword());
  const [roleId, setRoleId] = useState<number | "">("");

  const uid = emp.user_id;
  const reload = useCallback(() => {
    if (uid == null) {
      setRow(null);
      return;
    }
    api.rbac
      .users(token)
      .then((rows) => setRow(rows.find((u) => u.id === uid) ?? null))
      .catch(() => {});
    api.rbac
      .userSessions(token, uid)
      .then(setSessions)
      .catch(() => setSessions([]));
    api.rbac
      .userActivity(token, uid)
      .then(setActivity)
      .catch(() => setActivity([]));
  }, [token, uid]);
  useEffect(() => {
    reload();
  }, [reload]);

  const roleOpts = (meta?.roles ?? []).filter(
    (r) => r.department_id === emp.department_id,
  );

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      reload();
      onChanged();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  // --- Chưa có tài khoản → cấp tài khoản ---
  if (uid == null) {
    return (
      <div>
        {error && <div className="banner banner--error">{error}</div>}
        <InfoCard title="Chưa có tài khoản đăng nhập" icon={Key}>
          <p className="ns-info-field__label" style={{ gridColumn: "1 / -1" }}>
            Nhân viên chưa đăng nhập được vào hệ thống. Công nhân xưởng có thể
            không cần tài khoản.
          </p>
        </InfoCard>
        {canCreate && (
          <div className="ns-grid">
            <Field label="Tên đăng nhập *">
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="vd nguyenvana"
              />
            </Field>
            <Field label="Mật khẩu ban đầu *">
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            <Field label="Vai trò">
              <select
                value={roleId}
                onChange={(e) =>
                  setRoleId(e.target.value ? Number(e.target.value) : "")
                }
              >
                <option value="">
                  — chưa gán (đăng nhập nhưng chưa thấy gì) —
                </option>
                {roleOpts.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        )}
        {canCreate && (
          <div className="ns2-editfoot">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => setPassword(genPassword())}
              disabled={busy}
            >
              Tạo mật khẩu khác
            </button>
            <Button
              type="button"
              variant="accent"
              disabled={busy || !username.trim() || password.length < 6}
              onClick={() =>
                run(async () => {
                  await api.employees.createAccount(token, emp.id, {
                    username: username.trim(),
                    password,
                    role_id: roleId === "" ? null : roleId,
                  });
                  setTempPw(password);
                })
              }
            >
              {busy ? "Đang tạo…" : "Cấp tài khoản"}
            </Button>
          </div>
        )}
        {tempPw && (
          <div className="banner banner--ok">
            Đã cấp tài khoản. Mật khẩu ban đầu: <strong>{tempPw}</strong> — bàn
            giao cho nhân viên rồi đổi khi đăng nhập lần đầu.
          </div>
        )}
      </div>
    );
  }

  // --- Đã có tài khoản ---
  const locked = row !== null && !row.is_active;
  return (
    <div>
      {error && <div className="banner banner--error">{error}</div>}
      {tempPw && (
        <div className="banner banner--ok">
          Mật khẩu tạm: <strong>{tempPw}</strong> — mọi phiên đã bị thu hồi, bàn
          giao cho nhân viên.
        </div>
      )}
      <div className="ns-info-sections">
        <InfoCard title="Tài khoản" icon={Key}>
          <InfoField
            label="Tên đăng nhập"
            value={row?.username ?? emp.account_username}
            icon={User}
          />
          <InfoField
            label="Mã tài khoản"
            value={row?.code ?? null}
            icon={Hash}
          />
          <InfoField
            label="Trạng thái"
            value={locked ? "Đã khóa" : "Hoạt động"}
            icon={Lock}
          />
        </InfoCard>
        <InfoCard title="Vai trò" icon={Shield}>
          {canAssignRole ? (
            <div className="ns-info-field" style={{ gridColumn: "1 / -1" }}>
              <div className="ns-info-field__content" style={{ width: "100%" }}>
                <span className="ns-info-field__label">
                  Vai trò (theo phòng của hồ sơ)
                </span>
                <div className="ns-info-select-wrapper">
                  <select
                    value={row?.role_id ?? ""}
                    disabled={busy}
                    onChange={(e) => {
                      const v = e.target.value ? Number(e.target.value) : null;
                      run(() => api.rbac.assignUserRole(token, uid, v));
                    }}
                  >
                    <option value="">— chưa gán —</option>
                    {roleOpts.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.name}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="ns-info-select-chevron" size={14} />
                </div>
              </div>
            </div>
          ) : (
            <InfoField label="Vai trò" value={row?.role_name} icon={Shield} />
          )}
        </InfoCard>
      </div>

      <InfoCard title="Bảo mật" icon={Lock}>
        <div className="ns-detail__shortcuts" style={{ gridColumn: "1 / -1" }}>
          {canReset && (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const r = await api.rbac.resetUserPassword(token, uid);
                  setTempPw(r.temporary_password);
                })
              }
            >
              <Key size={12} /> Đặt lại mật khẩu
            </button>
          )}
          {canRevoke && (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              disabled={busy}
              onClick={() => run(() => api.rbac.revokeUserSessions(token, uid))}
            >
              <Lock size={12} /> Thu hồi mọi phiên
            </button>
          )}
          {canLock && (
            <button
              type="button"
              className={`btn btn--sm ${locked ? "btn--primary" : "btn--ghost ns-btn--danger"}`}
              disabled={busy}
              onClick={() =>
                run(() => api.rbac.setUserActive(token, uid, locked))
              }
            >
              <Lock size={12} />{" "}
              {locked ? "Mở khóa tài khoản" : "Khóa tài khoản"}
            </button>
          )}
        </div>
        <p className="ns-info-field__label" style={{ gridColumn: "1 / -1" }}>
          Nhân viên <strong>đã nghỉ việc</strong> tự động không đăng nhập được
          (theo trạng thái hồ sơ) — không cần khóa tay. Khóa dùng khi muốn chặn
          một người <strong>đang làm việc</strong>.
        </p>
      </InfoCard>

      <InfoCard
        title={`Phiên đang hoạt động (${sessions.length})`}
        icon={Activity}
      >
        {sessions.length === 0 ? (
          <InfoField label="Phiên" value={null} icon={Activity} />
        ) : (
          sessions.map((s) => (
            <InfoField
              key={s.id}
              label={deviceLabel(s.user_agent)}
              value={`Đăng nhập ${fmtDate(s.created_at)}`}
              icon={Activity}
            />
          ))
        )}
      </InfoCard>

      <InfoCard title="Hoạt động tài khoản gần đây" icon={Activity}>
        {activity.length === 0 ? (
          <InfoField label="Hoạt động" value={null} icon={Activity} />
        ) : (
          activity
            .slice(0, 8)
            .map((a) => (
              <InfoField
                key={a.id}
                label={`${a.action} · ${fmtDate(a.created_at)}`}
                value={a.actor_name ?? a.detail}
                icon={Activity}
              />
            ))
        )}
      </InfoCard>
    </div>
  );
}

function InfoCard({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: any;
  children: ReactNode;
}) {
  return (
    <div className="ns-info-card">
      <h4 className="ns-info-card__title">
        {Icon && <Icon size={14} />} {title}
      </h4>
      <div className="ns-info-grid">{children}</div>
    </div>
  );
}

function InfoField({
  label,
  value,
  icon: Icon,
  hint,
}: {
  label: string;
  value: string | null | undefined;
  icon?: any;
  hint?: string;
}) {
  return (
    <div className="ns-info-field">
      {Icon && <Icon className="ns-info-field__icon" size={14} />}
      <div className="ns-info-field__content">
        <span className="ns-info-field__label">{label}</span>
        {value ? (
          <span className="ns-info-field__value">{value}</span>
        ) : (
          <span className="ns-info-field__value ns-info-field__value--empty">
            —
          </span>
        )}
        {hint && <span className="ns-info-field__hint">{hint}</span>}
      </div>
    </div>
  );
}

function EventsTab({
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
    return v; // bậc tay nghề ("Bậc 2"), chức danh…
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

function FilesTab({
  token,
  employeeId,
  canUpdate,
}: {
  token: string;
  employeeId: number;
  canUpdate: boolean;
}) {
  const [items, setItems] = useState<EmployeeAttachment[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);
  const [activeKind, setActiveKind] = useState<string>("all");

  const load = useCallback(() => {
    setLoi(null);
    api.employees
      .attachments(token, employeeId)
      .then((r) => setItems(r.items))
      .catch((e) => {
        setItems([]);
        setLoi(errMsg(e));
      });
  }, [token, employeeId]);

  useEffect(() => {
    load();
  }, [load]);

  const counts = useMemo(() => {
    if (!items) return {};
    const res: Record<string, number> = { all: items.length };
    for (const item of items) {
      res[item.doc_kind] = (res[item.doc_kind] || 0) + 1;
    }
    return res;
  }, [items]);

  const filteredItems = useMemo(() => {
    if (!items) return [];
    if (activeKind === "all") return items;
    return items.filter((a) => a.doc_kind === activeKind);
  }, [items, activeKind]);

  const hasFiles = !!(items && items.length > 0);

  return (
    <div>
      {canUpdate && (
        <FilePicker
          disabled={busy}
          compact={hasFiles}
          defaultKind={activeKind !== "all" ? activeKind : "hop_dong"}
          onAdd={async (file, kind) => {
            setBusy(true);
            try {
              await api.employees.upload(token, employeeId, file, kind);
              load();
            } finally {
              setBusy(false);
            }
          }}
        />
      )}

      {busy && <p className="ns__empty">Đang tải tệp lên…</p>}
      {loi && <EmptyState trangThai="loi" loi={loi} onThuLai={load} />}
      {!loi && items === null && <EmptyState trangThai="dang-tai" />}

      {!loi && items !== null && (
        <>
          {/* Category Filter Chips Bar */}
          <div className="ns-file-filters">
            <button
              type="button"
              className={`ns-file-filter-chip ${activeKind === "all" ? "ns-file-filter-chip--active" : ""}`}
              onClick={() => setActiveKind("all")}
            >
              Tất cả
              <span className="ns-file-filter-chip__count">
                {counts["all"] || 0}
              </span>
            </button>
            {Object.entries(DOC_KIND_LABEL).map(([k, label]) => (
              <button
                key={k}
                type="button"
                className={`ns-file-filter-chip ${activeKind === k ? "ns-file-filter-chip--active" : ""}`}
                onClick={() => setActiveKind(k)}
              >
                {label}
                <span className="ns-file-filter-chip__count">
                  {counts[k] || 0}
                </span>
              </button>
            ))}
          </div>

          {/* Full-width List Rows */}
          {filteredItems.length === 0 ? (
            <p className="ns__empty" style={{ padding: "20px 0" }}>
              {activeKind === "all"
                ? "Chưa có tệp đính kèm nào."
                : `Chưa có tệp nào thuộc danh mục "${DOC_KIND_LABEL[activeKind]}".`}
            </p>
          ) : (
            <ul className="ns-filelist-v2">
              {filteredItems.map((a) => {
                const typeInfo = getFileTypeInfo(a.file_name);
                const IconComponent = typeInfo.icon;
                return (
                  <li key={a.id} className="ns-fileitem">
                    <div className={`ns-fileitem__icon ${typeInfo.className}`}>
                      <IconComponent size={18} />
                    </div>
                    <div className="ns-fileitem__main">
                      <div className="ns-fileitem__name-group">
                        <span className="ns-fileitem__name" title={a.file_name}>
                          {a.file_name}
                        </span>
                        <div className="ns-fileitem__sub">
                          <span>{fmtDate(a.uploaded_at)}</span>
                        </div>
                      </div>
                      <span className="ns-fileitem__badge">
                        {DOC_KIND_LABEL[a.doc_kind] ?? a.doc_kind}
                      </span>
                    </div>
                    <div className="ns-fileitem__actions">
                      <a
                        href={assetUrl(a.file_url) ?? "#"}
                        target="_blank"
                        rel="noreferrer"
                        className="btn btn--secondary btn--sm"
                        style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
                        title="Xem / Tải tệp"
                      >
                        <Eye size={13} /> Xem / Tải
                      </a>
                      {canUpdate && (
                        <button
                          type="button"
                          className="btn btn--ghost ns-danger btn--sm"
                          style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
                          title="Xóa tệp"
                          aria-label={`Xóa tệp ${a.file_name}`}
                          onClick={async () => {
                            if (
                              window.confirm(
                                `Bạn có chắc chắn muốn xóa tệp "${a.file_name}"?`,
                              )
                            ) {
                              await api.employees.deleteAttachment(
                                token,
                                employeeId,
                                a.id,
                              );
                              load();
                            }
                          }}
                        >
                          <Trash2 size={13} /> Xóa
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function ActivityTab({
  token,
  employeeId,
}: {
  token: string;
  employeeId: number;
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
  }, [load]);
  if (loi) return <EmptyState trangThai="loi" loi={loi} onThuLai={load} />;
  if (!items) return <EmptyState trangThai="dang-tai" />;
  const tl: TimelineEntry[] = items.map((a) => ({
    title: a.detail || a.action,
    meta: `${fmtDateTime(a.created_at)}${a.actor_name ? ` · ${a.actor_name}` : ""}`,
  }));
  return <Timeline items={tl} emptyText="Chưa có hoạt động." />;
}

// --- Action dialog (transition / transfer / promote / account) --------------

const ACTION_TITLE: Record<string, string> = {
  confirm: "Chuyển chính thức",
  leave_start: "Cho nghỉ dài hạn",
  leave_end: "Đi làm lại",
  suspend: "Đình chỉ",
  resign: "Cho nghỉ việc",
  reinstate: "Tuyển lại",
  transfer: "Điều chuyển phòng/tổ",
  promote: "Nâng bậc / đổi chức danh",
  link: "Nối tài khoản đăng nhập",
  unlink: "Gỡ tài khoản đăng nhập",
};

function ActionDialog({
  token,
  emp,
  meta,
  kind,
  onClose,
  onDone,
}: {
  token: string;
  emp: EmployeeDetail;
  meta: EmployeeMeta | null;
  kind: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const can = useCan();
  const canCreateGrade = can("nhan_su", "create");
  const jg = useJobGrades(token);
  const [effective, setEffective] = useState(today);
  const [note, setNote] = useState("");
  const [newDept, setNewDept] = useState<number | "">("");
  // KHÔNG preselect bậc hiện tại: danh mục chỉ trả bậc đang BẬT, người mang bậc đã tắt sẽ bị
  // select nhảy về option đầu rồi âm thầm đổi bậc lúc bấm Xác nhận.
  const [newJobGradeId, setNewJobGradeId] = useState<number | null>(null);
  const [newPos, setNewPos] = useState("");
  const [resignReason, setResignReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isTransition = true;
  const curGrade = emp.job_grade_name ?? emp.job_grade;
  // Người đang mang bậc (kể cả bậc kiểu cũ) vẫn phải sửa được bậc dù phòng chưa tick cờ SX.
  const showGrade =
    isProduction(meta, emp.department_id) ||
    emp.job_grade_id != null ||
    !!emp.job_grade;
  // Điều chuyển: backend XOÁ bậc khi không nhận `new_job_grade_id` (bậc tổ In vô nghĩa ở tổ Dán).
  const transferDropsGrade =
    kind === "transfer" &&
    !!curGrade &&
    newDept !== "" &&
    newJobGradeId == null;

  async function submit() {
    if (kind === "promote" && newJobGradeId == null && !newPos.trim()) {
      setError(
        showGrade
          ? "Chọn bậc tay nghề mới hoặc nhập chức danh mới."
          : "Nhập chức danh mới.",
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const input: EmployeeTransitionInput = {
        kind,
        effective_date: effective,
        note: note || undefined,
      };
      if (kind === "transfer") {
        input.new_department_id = newDept === "" ? undefined : newDept;
        input.new_job_grade_id = newJobGradeId ?? undefined;
      }
      if (kind === "promote") {
        input.new_job_grade_id = newJobGradeId ?? undefined;
        input.new_position = newPos || undefined;
      }
      if (kind === "resign") input.resign_reason = resignReason;
      await api.employees.transition(token, emp.id, input);
      onDone();
    } catch (e) {
      setError(errMsg(e));
      setBusy(false);
    }
  }

  return (
    <div className="ns-modal ns-modal--top" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>{ACTION_TITLE[kind] ?? kind}</h2>
          <button className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}

          {isTransition && (
            <Field label="Ngày hiệu lực">
              <input
                type="date"
                value={effective}
                onChange={(e) => setEffective(e.target.value)}
              />
            </Field>
          )}
          {kind === "transfer" && (
            <>
              <Field label="Phòng/Tổ mới *">
                <select
                  value={newDept}
                  onChange={(e) => {
                    setNewDept(
                      e.target.value === "" ? "" : Number(e.target.value),
                    );
                    setNewJobGradeId(null); // bậc khai theo TỔ MỚI → đổi tổ thì bỏ lựa chọn cũ
                  }}
                >
                  <option value="">— chọn —</option>
                  {meta?.departments
                    .filter((d) => d.id !== emp.department_id)
                    .map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                </select>
              </Field>
              {newDept !== "" && isProduction(meta, newDept) && (
                <JobGradeField
                  grades={jg.grades}
                  err={jg.err}
                  reload={jg.reload}
                  addGrade={jg.addGrade}
                  value={newJobGradeId}
                  onChange={setNewJobGradeId}
                  label="Bậc tay nghề ở tổ mới"
                  hint="Bậc khai lại theo tổ mới — bậc của tổ cũ không mang sang."
                  canCreate={canCreateGrade}
                />
              )}
              {transferDropsGrade && (
                <div className="banner banner--warn">
                  Chuyển tổ mà không chọn bậc ⇒ bậc hiện tại (<b>{curGrade}</b>)
                  sẽ bị <b>xoá khỏi hồ sơ</b>.
                </div>
              )}
            </>
          )}
          {kind === "promote" && (
            <>
              {showGrade && (
                <JobGradeField
                  grades={jg.grades}
                  err={jg.err}
                  reload={jg.reload}
                  addGrade={jg.addGrade}
                  value={newJobGradeId}
                  onChange={setNewJobGradeId}
                  label="Bậc tay nghề mới"
                  hint={curGrade ? `Đang ở: ${curGrade}` : "Chưa khai bậc."}
                  allowKeep
                  canCreate={canCreateGrade}
                />
              )}
              <Field label="Chức danh mới (tùy chọn)">
                <input
                  value={newPos}
                  onChange={(e) => setNewPos(e.target.value)}
                />
              </Field>
              <div className="ns-wizard__hint">
                Nâng bậc / đổi chức danh KHÔNG tự đổi tiền lương — bậc chỉ là
                khai báo. Muốn đổi mức thì sang Lương → Lương nhân viên → Sửa
                lương.
              </div>
            </>
          )}
          {kind === "resign" && (
            <Field label="Lý do nghỉ *">
              <input
                value={resignReason}
                onChange={(e) => setResignReason(e.target.value)}
              />
            </Field>
          )}
          {isTransition && kind !== "resign" && (
            <Field label="Ghi chú">
              <input value={note} onChange={(e) => setNote(e.target.value)} />
            </Field>
          )}
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <Button variant="accent" onClick={submit} loading={busy}>
            {busy ? "Đang xử lý…" : "Xác nhận"}
          </Button>
        </footer>
      </div>
    </div>
  );
}
