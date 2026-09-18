// Hồ sơ nhân sự (module `nhan_su`, lát #1). Danh sách + KPI + Wizard thêm (5 bước) +
// Trang hồ sơ (tab Thông tin / Quá trình công tác / Đính kèm / Nhật ký) + dialog Đổi
// trạng thái / Điều chuyển / Đổi chức danh (sinh Quá trình công tác) + nối/tạo tài khoản.
// Backend là cổng quyền thật (403); useCan chỉ ẩn/hiện nút cho gọn UX.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  assetUrl,
  type EmployeeKpis,
  type EmployeeMeta,
  type EmployeeRow,
} from "../../../api/client";
import { Button } from "../../../components/Button";
import { EmptyRow, EmptyState } from "../../../components/EmptyState";
import { useAuth } from "../../../auth/useAuth";
import { useCan } from "../../../auth/permissions";
// `fmtDate` DÙNG CHUNG (utils/format) — trước đây file này tự chép một bản y hệt.
// Đừng viết lại bản cục bộ: sửa cách hiện ngày ở một chỗ mà nửa hệ thống không đổi theo.
import { fmtDate } from "../../../utils/format";
import type { NavigateFn } from "../../../components/AppShell";
import {
  Activity,
  ChevronDown,
  Download,
  Key,
  Search,
  Upload,
  UserPlus,
  X,
} from "lucide-react";
import { STATUS_LABEL } from "./shared/constants";
import { errMsg, getAvatarClass } from "./shared/helpers";
import { KpiStrip, StatusBadge } from "./components/badges";
import { RequestQueueModal } from "./modals/RequestQueueModal";
import { EmployeeDetailPanel } from "./EmployeeDetailPanel";
import { EmployeeWizard } from "./EmployeeWizard";
import { ImportExcelDialog } from "../../../components/ImportExcelDialog";
import "../../nhan-su.css";

export function NhanSuPage({ navigate }: { navigate?: NavigateFn }) {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("nhan_su", "create");
  const canApprove = can("nhan_su", "approve");
  const canSalary = can("nhan_su", "edit_salary"); // có quyền khai lương → hiện bước "Lương" khi thêm NV
  // Ô "Xuất Excel danh sách". Trước 11/08/2026 nút render TRẦN, không hỏi quyền gì — nên ô đó
  // trong ma trận chưa bao giờ có tác dụng. Máy chủ cũng đã siết sang `nhan_su:export`.
  const canExport = can("nhan_su", "export");
  // Nhập Excel đòi CẢ create lẫn update (cùng luật với nhập Excel danh mục): một lượt nhập vừa
  // tạo người mới vừa sửa người cũ, có đúng một trong hai ô là không đủ. Máy chủ gác y hệt.
  const canImport = can("nhan_su", "create") && can("nhan_su", "update");

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
  /** Chữ đã NGỪNG gõ 300ms mới đem đi hỏi máy chủ — gõ "Nguyễn" là 6 lượt tải nếu không chờ. */
  const [qDebounced, setQDebounced] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);
  const [statusFilter, setStatusFilter] = useState("");
  const [deptFilter, setDeptFilter] = useState<number | "">("");
  const [accountFilter, setAccountFilter] = useState(""); // "" | "yes" | "no"
  const [sort, setSort] = useState("code");
  // KPI "sắp hết thử việc" — lọc ở MÁY CHỦ. Trước đây lọc trên trình duyệt trong đúng trang 20
  // người đang tải: ai sắp hết thử việc mà nằm ở trang 2 thì không bao giờ hiện, và "Tổng" vẫn
  // đếm cả người không khớp.
  const [endingSoon, setEndingSoon] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
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

  /** Số thứ tự lượt tải danh sách. Đổi 2 bộ lọc liền tay là 2 request bay song song; phản hồi
   *  của lượt CŨ về sau đè lượt mới ⇒ bảng hiện sai bộ lọc đang chọn (test luồng 08/09/2026).
   *  Chỉ nhận phản hồi của lượt mới nhất. */
  const luotTai = useRef(0);
  const load = useCallback(() => {
    if (!token) return;
    const luot = ++luotTai.current;
    setLoading(true);
    api.employees
      .list(token, {
        q: qDebounced || undefined,
        status: statusFilter || undefined,
        department_id: deptFilter === "" ? undefined : deptFilter,
        has_account: accountFilter === "" ? undefined : accountFilter === "yes",
        ending_soon: endingSoon || undefined,
        sort,
        page,
        size,
      })
      .then((res) => {
        if (luot !== luotTai.current) return;
        setData({ items: res.items, total: res.total, kpis: res.kpis });
        setListError(null);
      })
      .catch((e) => {
        if (luot === luotTai.current) setListError(errMsg(e));
      })
      .finally(() => {
        if (luot === luotTai.current) setLoading(false);
      });
  }, [token, qDebounced, statusFilter, deptFilter, accountFilter, endingSoon, sort, page]);

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
      // ĐỦ mọi bộ lọc của bảng — trước đây thiếu "Tài khoản" và "Sắp hết thử việc" nên file ra
      // nhiều người hơn con số "Tổng" trên màn.
      const url = await api.employees.exportXlsxBlobUrl(token, {
        q: q.trim() || undefined,
        status: statusFilter || undefined,
        department_id: deptFilter === "" ? undefined : deptFilter,
        has_account: accountFilter === "" ? undefined : accountFilter === "yes",
        ending_soon: endingSoon || undefined,
        sort,
      });
      const a = document.createElement("a");
      a.href = url;
      a.download = "ho-so-nhan-su.xlsx";
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

  /** File MẪU để nạp dữ liệu ban đầu — đúng tiêu đề file xuất, không kèm ai, cộng sheet Hướng dẫn
   *  liệt kê tên phòng/tổ · bậc · ca hợp lệ. Người chưa có ai trong hệ thống vẫn có file để khai. */
  async function taiMauNhap() {
    if (!token) return;
    try {
      const url = await api.employees.mauNhapBlobUrl(token);
      const a = document.createElement("a");
      a.href = url;
      a.download = "mau-nhap-nhan-su.xlsx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setError("Không tải được file mẫu.");
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
  const rows = data?.items ?? [];

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
                setPage(1);
                setEndingSoon(false);
                setStatusFilter("");
              }}
              onPickProbation={() => {
                setPage(1);
                setEndingSoon(false);
                setStatusFilter("probation");
              }}
              onPickProbationEnded={() => {
                setPage(1);
                setEndingSoon(false);
                setStatusFilter("probation_ended");
              }}
              onPickActive={() => {
                setPage(1);
                setEndingSoon(false);
                setStatusFilter("active");
              }}
              onPickEndingSoon={() => {
                setPage(1);
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
                  className="ns-search-clear"
                  onClick={() => {
                    setQ("");
                    setPage(1);
                  }}
                  title="Xóa tìm kiếm"
                  aria-label="Xóa tìm kiếm"
                >
                  <X size={14} />
                </button>
              )}
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
            {canImport && (
              <button className="ns-btn-excel" onClick={() => setImportOpen(true)}>
                <Upload size={14} />
                Nhập Excel
              </button>
            )}
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
                  <th>Ngày vào làm</th>
                  <th>Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {loading && <EmptyRow colSpan={6} trangThai="dang-tai" />}
                {!loading && listError && (
                  <EmptyRow
                    colSpan={6}
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
                        <td className="ns-cell-date">{fmtDate(e.hire_date)}</td>
                        <td>
                          <StatusBadge status={e.status} />
                        </td>
                      </tr>
                    );
                  })}
                {!loading && !listError && rows.length === 0 && (
                  <EmptyRow
                    colSpan={6}
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

          {/* Dạng thẻ Mobile (< 768px) hỗ trợ cảm ứng tiện dụng */}
          <div className="ns-cards-wrapper">
            {loading && <EmptyState trangThai="dang-tai" />}
            {!loading && listError && (
              <EmptyState
                trangThai="loi"
                loi={listError}
                onThuLai={load}
              />
            )}
            {!loading && !listError && rows.length === 0 && (
              <EmptyState
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
            {!loading &&
              !listError &&
              rows.map((e) => {
                const avatarClass = getAvatarClass(e.full_name);
                const photoSrc = assetUrl(e.photo_url);
                return (
                  <div
                    key={e.id}
                    className="ns-mobile-card"
                    onClick={() => setSelectedId(e.id)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(ev) => {
                      if (ev.key === "Enter" || ev.key === " ") {
                        ev.preventDefault();
                        setSelectedId(e.id);
                      }
                    }}
                  >
                    <div className="ns-mobile-card__head">
                      <div className="ns-avatar-wrapper">
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
                      <div className="ns-mobile-card__title-col">
                        <div className="ns-mobile-card__title-row">
                          <span className="ns-mobile-card__name">{e.full_name}</span>
                          {e.account_username && (
                            <span title={`Tài khoản: ${e.account_username}`}>
                              <Key size={13} style={{ marginLeft: "2px" }} />
                            </span>
                          )}
                        </div>
                        <span className="ns-code-chip">{e.code}</span>
                      </div>
                      <div className="ns-mobile-card__badge-col">
                        <StatusBadge status={e.status} />
                      </div>
                    </div>
                    <div className="ns-mobile-card__meta-grid">
                      <div className="ns-mobile-card__meta-item">
                        <span className="ns-mobile-card__meta-label">Phòng/Tổ</span>
                        <span className="ns-mobile-card__meta-val">{e.department_name ?? "—"}</span>
                      </div>
                      <div className="ns-mobile-card__meta-item">
                        <span className="ns-mobile-card__meta-label">Chức danh</span>
                        <span className="ns-mobile-card__meta-val">{e.role_name ?? e.position ?? "—"}</span>
                      </div>
                      <div className="ns-mobile-card__meta-item">
                        <span className="ns-mobile-card__meta-label">Ngày vào</span>
                        <span className="ns-mobile-card__meta-val ns-num">{fmtDate(e.hire_date)}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
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
        <EmployeeDetailPanel
          token={token!}
          employeeId={selectedId}
          meta={meta}
          navigate={navigate}
          onClose={() => setSelectedId(null)}
          onChanged={load}
        />
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

      {importOpen && token && (
        <ImportExcelDialog
          ten="hồ sơ nhân sự"
          chay={(f, mode) => api.employees.importExcel(token, f, mode)}
          taiMau={taiMauNhap}
          luat={
            "Bấm “Tải file mẫu” để lấy file trắng đúng định dạng, hoặc “Xuất Excel” " +
            "để lấy file có sẵn người hiện có rồi sửa trên chính file đó. Mã đã có là sửa đúng " +
            "người đó; mã CHƯA có là thêm người mới GIỮ NGUYÊN mã đó (chuyển dữ liệu sang máy " +
            "khác thì mã không bị cấp lại); để TRỐNG ô Mã thì máy tự cấp NV001, NV002… Cột không " +
            "có trong file thì giữ nguyên, ô trống ở cột CÓ trong file thì xoá giá trị — riêng " +
            "Thâm niên trước, Số người phụ thuộc, Cách tính thuế TNCN thì về mặc định (0 · 0 · " +
            "Luỹ tiến). Ai không có mặt " +
            "trong file thì không bị đụng tới. Cả file là MỘT lượt: còn một dòng lỗi thì không ghi " +
            "gì cả. Trạng thái của người đã có và tài khoản đăng nhập thì file không đổi được — " +
            "làm trên màn."
          }
          onClose={() => setImportOpen(false)}
          onImported={() => { setImportOpen(false); load(); }}
        />
      )}

      {reqOpen && (
        <RequestQueueModal
          token={token!}
          onClose={() => setReqOpen(false)}
          onCount={setReqCount}
          // Duyệt là ghi vào hồ sơ (tên, phòng… đều là cột của bảng) ⇒ tải lại danh sách. Trước
          // đây chỉ tải lại khi ĐANG mở một hồ sơ, nên duyệt từ màn danh sách thì bảng vẫn chữ cũ.
          onDecided={(approved) => {
            if (approved) load();
          }}
        />
      )}
    </main>
  );
}
