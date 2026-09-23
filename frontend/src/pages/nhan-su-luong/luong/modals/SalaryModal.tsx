// Modal khai báo & điều chỉnh lương của một nhân viên (tách từ pages/LuongPage.tsx).
import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  CreditCard,
  DollarSign,
  History,
  Plus,
  Shield,
  Sparkles,
  X,
} from "lucide-react";
import "../../../nhan-su.css";
import "../../../luong.css";
import {
  api,
  assetUrl,
  type EmployeeRow,
  type EmployeeSalary,
  type PayrollComponent,
  type PayrollParams,
  type SalaryPreview,
} from "../../../../api/client";
import { fmtDateTime } from "../../../../utils/format";
import { ConfirmDialog } from "../../../../components/ConfirmDialog";
import { EmptyRow } from "../../../../components/EmptyState";
import type { CompRow } from "../shared/types";
import { errText, fmtYmd, money, todayYmd } from "../shared/helpers";

export function SalaryModal({
  token,
  emp,
  onClose,
}: {
  token: string;
  emp: EmployeeRow;
  onClose: () => void;
}) {
  const [, setPreview] = useState<SalaryPreview | null>(null);
  const [history, setHistory] = useState<EmployeeSalary[] | null>(null);
  const [histErr, setHistErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  // Auto-dismiss success notification after 4s
  useEffect(() => {
    if (!ok) return;
    const t = setTimeout(() => setOk(null), 4000);
    return () => clearTimeout(t);
  }, [ok]);

  // Tab navigation
  const [activeTab, setActiveTab] = useState<
    "salary" | "insurance" | "history"
  >("salary");

  // Salary fields
  const [luongViTri, setLuongViTri] = useState(0);
  const [luongTrachNhiem, setLuongTrachNhiem] = useState(0);
  const [mucDongBh, setMucDongBh] = useState<number | null>(null);
  const [luongDot1, setLuongDot1] = useState(0);
  const [commissionPct, setCommissionPct] = useState(0);
  const [allowance, setAllowance] = useState(0);
  const [chuyenCan, setChuyenCan] = useState(0);
  const [phuCapCa, setPhuCapCa] = useState(0);
  const [phuCapThamNien, setPhuCapThamNien] = useState(0);

  // Recurring components
  const [comps, setComps] = useState<CompRow[] | null>(null);
  const [compBusy, setCompBusy] = useState<number | null>(null);
  const [compsErr, setCompsErr] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<PayrollComponent[] | null>(null);
  const [catalogErr, setCatalogErr] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const [confirmDeleteComp, setConfirmDeleteComp] = useState<CompRow | null>(
    null,
  );

  // Insurance & Union flags
  const [insuranceElsewhere, setInsuranceElsewhere] = useState(false);
  const [unionMember, setUnionMember] = useState(false);
  const [applySelfDeduction] = useState(true);
  const [params, setParams] = useState<PayrollParams | null>(null);

  const reload = useCallback(async () => {
    const [prev, hist] = await Promise.all([
      api.luong.salaryPreview(token, emp.id).catch(() => null),
      api.luong.salaries(token, emp.id).catch((e) => {
        setHistErr(errText(e));
        return null;
      }),
    ]);
    setPreview(prev);
    if (!hist) return;
    setHistErr(null);
    setHistory(hist.items);

    const latest = hist.items.length
      ? [...hist.items].sort((a, b) =>
          b.effective_from.localeCompare(a.effective_from),
        )[0]
      : null;
    if (latest) {
      setAllowance(latest.allowance ?? 0);
      setChuyenCan(latest.chuyen_can ?? 0);
      setPhuCapCa(latest.phu_cap_ca ?? 0);
      setPhuCapThamNien(latest.phu_cap_tham_nien ?? 0);
      setLuongDot1(latest.luong_dot_1 ?? 0);
      setCommissionPct((latest.commission_pct ?? 0) * 100);
      setMucDongBh(
        latest.insurance_base && latest.insurance_base > 0
          ? latest.insurance_base
          : null,
      );
      setInsuranceElsewhere(!!latest.insurance_elsewhere);
      setUnionMember(!!latest.union_member);

      const vt = latest.luong_vi_tri ?? 0;
      const tn = latest.luong_trach_nhiem ?? 0;
      if (vt > 0 || tn > 0) {
        setLuongViTri(vt);
        setLuongTrachNhiem(tn);
      } else {
        setLuongViTri(latest.base_amount ?? 0);
        setLuongTrachNhiem(0);
      }
    }
  }, [token, emp.id]);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    api.luong
      .getParams(token)
      .then(setParams)
      .catch(() => setParams(null));
  }, [token]);

  const loadComps = useCallback(async () => {
    try {
      const r = await api.luong.components.employeeValues(token, emp.id);
      setComps(
        r.items.map((v) => ({
          component_id: v.component_id,
          name: v.name,
          kind: v.kind,
          is_taxable: v.is_taxable,
          is_active: v.is_active,
          saved: v.amount,
          savedNote: v.note,
          draft: v.amount,
          note: v.note ?? "",
        })),
      );
      setCompsErr(null);
    } catch (e) {
      setCompsErr(errText(e));
    }
  }, [token, emp.id]);

  useEffect(() => {
    loadComps();
  }, [loadComps]);

  useEffect(() => {
    let alive = true;
    api.luong.components
      .list(token)
      .then((r) => {
        if (!alive) return;
        setCatalog(r.items);
        setCatalogErr(null);
      })
      .catch((e) => {
        if (!alive) return;
        setCatalogErr(errText(e));
      });
    return () => {
      alive = false;
    };
  }, [token]);

  function setRow(id: number, patch: Partial<CompRow>) {
    setComps((list) =>
      (list ?? []).map((r) =>
        r.component_id === id ? { ...r, ...patch } : r,
      ),
    );
  }

  const assigned = new Set((comps ?? []).map((r) => r.component_id));
  const addable = (catalog ?? []).filter(
    (c) => c.is_active && !assigned.has(c.id),
  );

  function addComp(componentId: number) {
    const c = (catalog ?? []).find((x) => x.id === componentId);
    if (!c) return;
    setComps((list) => [
      ...(list ?? []),
      {
        component_id: c.id,
        name: c.name,
        kind: c.kind,
        is_taxable: c.is_taxable,
        is_active: c.is_active,
        saved: null,
        savedNote: null,
        draft: 0,
        note: "",
      },
    ]);
    setPicking(false);
  }

  async function removeComp(row: CompRow) {
    if (row.saved === null) {
      setComps((list) =>
        (list ?? []).filter((r) => r.component_id !== row.component_id),
      );
      return;
    }
    setCompBusy(row.component_id);
    setErr(null);
    try {
      await api.luong.components.setEmployeeValues(token, emp.id, [
        { component_id: row.component_id, amount: null },
      ]);
      setComps((list) =>
        (list ?? []).filter((r) => r.component_id !== row.component_id),
      );
      setOk(
        `Đã gỡ khoản “${row.name}” khỏi ${emp.full_name}. Kỳ lương đã chốt giữ nguyên số cũ.`,
      );
    } catch (e) {
      setErr(errText(e));
    } finally {
      setCompBusy(null);
    }
  }

  const compChanged = (comps ?? []).filter(
    (r) =>
      r.saved === null ||
      r.draft !== r.saved ||
      (r.note.trim() || null) !== r.savedNote,
  );

  async function doSave() {
    const emptyNew = compChanged.find((r) => r.saved === null && r.draft <= 0);
    if (emptyNew) {
      setErr(
        `Nhập số tiền cho khoản “${emptyNew.name}” (hoặc bấm Gỡ để bỏ dòng đó) rồi lưu lại.`,
      );
      return;
    }
    if ((mucDongBh ?? 0) <= 0 && !insuranceElsewhere) {
      setErr(
        "Mức đóng BHXH là bắt buộc — mỗi người một mức, không được để 0. Nếu người này đóng đúng " +
          "mức nền thì gõ lại đúng số mức nền.",
      );
      return;
    }
    setBusy(true);
    setErr(null);
    setOk(null);
    try {
      const eff = todayYmd();
      await api.luong.setSalary(token, emp.id, {
        effective_from: eff,
        luong_vi_tri: luongViTri,
        luong_trach_nhiem: luongTrachNhiem,
        insurance_base: mucDongBh ?? 0,
        luong_dot_1: luongDot1,
        allowance,
        chuyen_can: chuyenCan,
        phu_cap_ca: phuCapCa,
        phu_cap_tham_nien: phuCapThamNien,
        insurance_elsewhere: insuranceElsewhere,
        union_member: unionMember,
        apply_self_deduction: applySelfDeduction,
        commission_pct: Math.min(commissionPct, 100) / 100,
      });

      if (compChanged.length) {
        await api.luong.components.setEmployeeValues(
          token,
          emp.id,
          compChanged.map((r) => ({
            component_id: r.component_id,
            amount: r.draft,
            note: r.note.trim() || null,
          })),
        );
        await loadComps();
      }

      setOk(
        "Đã lưu lương thành công (hiệu lực từ hôm nay " + fmtYmd(eff) + ").",
      );
      reload();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }

  // Calculated metrics
  const salaryBase = luongViTri + luongTrachNhiem;
  const bhBase = (mucDongBh ?? 0) > 0 ? (mucDongBh as number) : salaryBase;

  const compThu = (comps ?? []).reduce(
    (s, r) => (r.kind === "thu" ? s + r.draft : s),
    0,
  );
  const compTru = (comps ?? []).reduce(
    (s, r) => (r.kind === "tru" ? s + r.draft : s),
    0,
  );
  const sysThu = luongViTri + luongTrachNhiem + chuyenCan + allowance;
  const isProbation = emp.status === "probation";

  // Insurance calculation
  const bhCapY =
    params && params.bh_base_cap > 0
      ? Math.min(bhBase, params.bh_base_cap)
      : bhBase;
  const bhCapTN =
    params && params.bhtn_base_cap > 0
      ? Math.min(bhBase, params.bhtn_base_cap)
      : bhBase;

  const bhxhRate = params?.bhxh_rate ?? 0.08;
  const bhytRate = params?.bhyt_rate ?? 0.015;
  const bhtnRate = params?.bhtn_rate ?? 0.01;

  const bhxhErRate = params?.bhxh_rate_er ?? 0.175;
  const bhytErRate = params?.bhyt_rate_er ?? 0.03;
  const bhtnErRate = params?.bhtn_rate_er ?? 0.01;
  const tnldBnnRate = params?.tnld_bnn_rate ?? 0.005;

  const bhxhAmt = bhCapY * bhxhRate;
  const bhytAmt = bhCapY * bhytRate;
  const bhtnAmt = bhCapTN * bhtnRate;
  const unionFeeAmt = unionMember ? Math.round(salaryBase * 0.01) : 0;
  const bhTotal = bhxhAmt + bhytAmt + bhtnAmt;

  const erBhxhAmt = bhCapY * bhxhErRate;
  const erBhytAmt = bhCapY * bhytErRate;
  const erBhtnAmt = bhCapTN * bhtnErRate;
  const erTnldAmt = bhBase * tnldBnnRate;
  const erTotal = erBhxhAmt + erBhytAmt + erBhtnAmt + erTnldAmt;

  const pctOf = (r: number) =>
    (r * 100).toLocaleString("vi-VN", { maximumFractionDigits: 2 });

  // Status mapping
  const statusLabels: Record<string, { label: string; className: string }> = {
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
  const statusInfo = statusLabels[emp.status] ?? {
    label: emp.status,
    className: "ns-badge ns-badge--muted",
  };
  const photoSrc = assetUrl(emp.photo_url);

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box ns-modal__box--salary-edit">
        {/* 1. Header with Employee Card */}
        <div className="lg-modal-emp-card">
          <div className="lg-modal-emp-left">
            {photoSrc ? (
              <img
                src={photoSrc}
                alt={emp.full_name}
                className="lg-modal-emp-avatar"
              />
            ) : (
              <div className="lg-modal-emp-avatar">
                {emp.full_name.trim().slice(0, 1).toUpperCase()}
              </div>
            )}
            <div className="lg-modal-emp-info">
              <div className="lg-modal-emp-title-row">
                <span className="lg-modal-emp-name">{emp.full_name}</span>
                <span className="ns-code-chip">{emp.code}</span>
                <span className={statusInfo.className}>
                  {statusInfo.label}
                </span>
              </div>
              <div className="lg-modal-emp-meta">
                <span>
                  Phòng/Tổ: <b>{emp.department_name ?? "Chưa phân phòng"}</b>
                </span>
                {emp.position && (
                  <span>
                    · Vị trí: <b>{emp.position}</b>
                  </span>
                )}
              </div>
            </div>
          </div>
          <button
            type="button"
            className="ns-modal__x"
            onClick={onClose}
            aria-label="Đóng"
          >
            ×
          </button>
        </div>

        {/* Modal Tab Nav */}
        <div className="lg-modal-tab-nav">
          <button
            type="button"
            className={`lg-modal-tab-item ${activeTab === "salary" ? "is-active" : ""}`}
            onClick={() => setActiveTab("salary")}
          >
            <DollarSign size={15} />
            <span>Mức lương &amp; Phụ cấp</span>
          </button>
          <button
            type="button"
            className={`lg-modal-tab-item ${activeTab === "insurance" ? "is-active" : ""}`}
            onClick={() => setActiveTab("insurance")}
          >
            <Shield size={15} />
            <span>Bảo hiểm &amp; Công đoàn</span>
          </button>
          <button
            type="button"
            className={`lg-modal-tab-item ${activeTab === "history" ? "is-active" : ""}`}
            onClick={() => setActiveTab("history")}
          >
            <History size={15} />
            <span>Lịch sử điều chỉnh</span>
            {history && history.length > 0 && (
              <span
                className="ns-badge ns-badge--muted"
                style={{ marginLeft: 4, fontSize: 11, padding: "1px 6px" }}
              >
                {history.length}
              </span>
            )}
          </button>
        </div>

        <div className="ns-modal__body">
          {/* Toast / Notification Alert */}
          {ok && (
            <div className="lg-modal-alert lg-modal-alert--success" role="alert">
              <div className="lg-modal-alert-icon">
                <CheckCircle2 size={18} />
              </div>
              <div className="lg-modal-alert-body">
                <div className="lg-modal-alert-title">Thao tác thành công</div>
                <div className="lg-modal-alert-msg">{ok}</div>
              </div>
              <button
                type="button"
                className="lg-modal-alert-close"
                onClick={() => setOk(null)}
                aria-label="Đóng thông báo"
              >
                <X size={15} />
              </button>
            </div>
          )}

          {err && (
            <div className="lg-modal-alert lg-modal-alert--error" role="alert">
              <div className="lg-modal-alert-icon">
                <AlertCircle size={18} />
              </div>
              <div className="lg-modal-alert-body">
                <div className="lg-modal-alert-title">Không thể thực hiện</div>
                <div className="lg-modal-alert-msg">{err}</div>
              </div>
              <button
                type="button"
                className="lg-modal-alert-close"
                onClick={() => setErr(null)}
                aria-label="Đóng thông báo"
              >
                <X size={15} />
              </button>
            </div>
          )}

          {/* 2. Executive KPI Ribbon / 4 Metric Cards */}
          <div className="lg-kpi-ribbon">
            <div className="lg-kpi-card">
              <div className="lg-kpi-card-header">
                <div
                  className="lg-kpi-card-icon"
                  style={{
                    background: "rgba(59, 130, 246, 0.1)",
                    color: "#2563eb",
                  }}
                >
                  <DollarSign size={16} />
                </div>
                <span className="lg-kpi-card-label">Mức nền hợp đồng</span>
              </div>
              <div className="lg-kpi-card-val">{money(salaryBase)} đ</div>
              <div className="lg-kpi-card-sub">Cơ bản + Trách nhiệm</div>
            </div>

            <div className="lg-kpi-card">
              <div className="lg-kpi-card-header">
                <div
                  className="lg-kpi-card-icon"
                  style={{
                    background: "rgba(16, 185, 129, 0.1)",
                    color: "#059669",
                  }}
                >
                  <Sparkles size={16} />
                </div>
                <span className="lg-kpi-card-label">Phụ cấp &amp; Thưởng</span>
              </div>
              <div className="lg-kpi-card-val">
                {money(chuyenCan + compThu)} đ
              </div>
              <div className="lg-kpi-card-sub">
                Chuyên cần: {money(chuyenCan)} · Khoản: {money(compThu)}
              </div>
            </div>

            <div className="lg-kpi-card">
              <div className="lg-kpi-card-header">
                <div
                  className="lg-kpi-card-icon"
                  style={{
                    background: "rgba(245, 158, 11, 0.1)",
                    color: "#d97706",
                  }}
                >
                  <CreditCard size={16} />
                </div>
                <span className="lg-kpi-card-label">Tổng thu nhập tháng</span>
              </div>
              <div className="lg-kpi-card-val">
                {money(sysThu + compThu - compTru)} đ
              </div>
              <div className="lg-kpi-card-sub">Dự kiến trước thuế &amp; BH</div>
            </div>

            <div className="lg-kpi-card">
              <div className="lg-kpi-card-header">
                <div
                  className="lg-kpi-card-icon"
                  style={{
                    background: "rgba(139, 92, 246, 0.1)",
                    color: "#7c3aed",
                  }}
                >
                  <Shield size={16} />
                </div>
                <span className="lg-kpi-card-label">Mức đóng BHXH</span>
              </div>
              <div className="lg-kpi-card-val">
                {insuranceElsewhere
                  ? "Đóng nơi khác"
                  : mucDongBh
                    ? `${money(mucDongBh)} đ`
                    : "Chưa khai"}
              </div>
              <div className="lg-kpi-card-sub">
                {insuranceElsewhere
                  ? "Chỉ đóng TNLĐ-BNN"
                  : mucDongBh
                    ? "Theo mức hợp đồng"
                    : "Tạm theo mức nền"}
              </div>
            </div>
          </div>

          {/* 3. Tab Contents */}

          {/* Tab 1: Mức lương & Phụ cấp */}
          {activeTab === "salary" && (
            <div className="lg-modal-tab-content">
              <div className="lg-form-card">
                <div className="lg-form-card__title">
                  Lương cơ bản &amp; Lương trách nhiệm
                </div>
                <div className="ns-grid">
                  <label className="ns-field">
                    <span className="ns-field__label">Lương cơ bản *</span>
                    <input
                      type="number"
                      min={0}
                      step={100000}
                      aria-label="Lương cơ bản"
                      value={luongViTri}
                      onChange={(e) => setLuongViTri(Number(e.target.value))}
                    />
                    <span className="cc-card__hint">
                      Lương theo công và tăng ca tính trên mức nền (cơ bản +
                      trách nhiệm).
                    </span>
                  </label>

                  <label className="ns-field">
                    <span className="ns-field__label">Lương trách nhiệm</span>
                    <input
                      type="number"
                      min={0}
                      step={100000}
                      aria-label="Lương trách nhiệm"
                      value={luongTrachNhiem}
                      onChange={(e) =>
                        setLuongTrachNhiem(Number(e.target.value))
                      }
                    />
                    <span className="cc-card__hint">
                      Mức nền = cơ bản + trách nhiệm:{" "}
                      <b>{money(salaryBase)} đ</b>.
                    </span>
                  </label>
                </div>

                <div className="ns-grid" style={{ marginTop: 12 }}>
                  <label className="ns-field">
                    <span className="ns-field__label">Thưởng chuyên cần</span>
                    <input
                      type="number"
                      min={0}
                      step={50000}
                      aria-label="Thưởng chuyên cần"
                      value={chuyenCan}
                      onChange={(e) => setChuyenCan(Number(e.target.value))}
                    />
                    <span className="cc-card__hint">
                      Để 0 = không có chuyên cần. Trừ dần theo ngày nghỉ trong
                      tháng.
                    </span>
                  </label>
                </div>
              </div>

              {/* Khoản thu nhập theo danh mục */}
              <div className="lg-form-card">
                <div className="lg-form-card__title">
                  Khoản thu nhập theo danh mục
                </div>
                <p className="cc-note">
                  Khoản gán ở đây được trả <b>lặp lại mọi tháng</b> cho tới khi
                  bạn gỡ. Chip <b>Chịu thuế / Miễn thuế</b> kế thừa từ danh mục
                  gốc — không sửa ở đây.
                </p>

                <div className="lg-comp lg-comp--cat">
                  <div className="lg-comp__head">
                    <span>Khoản thu nhập</span>
                    <span>Thuế TNCN</span>
                    <span style={{ textAlign: "right" }}>Số tiền / tháng</span>
                    <span>Ghi chú</span>
                    <span style={{ textAlign: "center" }}>Gỡ</span>
                  </div>
                  {comps === null ? (
                    <div className="lg-comp__empty">
                      {compsErr ? (
                        <>
                          Không đọc được khoản của người này ({compsErr}).{" "}
                          <button
                            type="button"
                            className="lg-linkbtn"
                            onClick={() => void loadComps()}
                          >
                            Thử lại
                          </button>
                        </>
                      ) : (
                        "Đang tải các khoản đang gán…"
                      )}
                    </div>
                  ) : comps.length === 0 ? (
                    <div className="lg-comp__empty">
                      Người này chưa được gán khoản thu nhập nào. Bấm{" "}
                      <b>“+ Thêm khoản từ danh mục”</b> để chọn từ danh mục.
                    </div>
                  ) : (
                    comps.map((r) => (
                      <div
                        key={r.component_id}
                        className={`lg-comp__row${r.is_active ? "" : " lg-comp__row--off"}`}
                      >
                        <div className="lg-comp__name">
                          <span>{r.name}</span>
                          {r.kind === "tru" && (
                            <span
                              className="ns-badge ns-badge--danger"
                              style={{ marginLeft: 6 }}
                            >
                              Trừ
                            </span>
                          )}
                          {r.saved === null && (
                            <span
                              className="ns-badge ns-badge--muted"
                              style={{ marginLeft: 6 }}
                            >
                              mới
                            </span>
                          )}
                          {!r.is_active && (
                            <span className="lg-comp__warn">
                              Khoản này đã ngừng áp dụng. Gỡ bỏ hoặc để 0.
                            </span>
                          )}
                        </div>
                        <div>
                          <span
                            className={`ns-badge ${r.is_taxable ? "ns-badge--info" : "ns-badge--ok"}`}
                          >
                            {r.is_taxable ? "Chịu thuế" : "Miễn thuế"}
                          </span>
                        </div>
                        <div className="lg-comp__money">
                          <input
                            type="number"
                            min={0}
                            step={50000}
                            aria-label={`Số tiền khoản ${r.name}`}
                            value={r.draft}
                            disabled={compBusy === r.component_id}
                            onChange={(e) =>
                              setRow(r.component_id, {
                                draft: Number(e.target.value),
                              })
                            }
                          />
                        </div>
                        <div className="lg-comp__note">
                          <input
                            type="text"
                            maxLength={255}
                            placeholder="Ghi chú áp dụng…"
                            aria-label={`Ghi chú khoản ${r.name}`}
                            value={r.note}
                            disabled={compBusy === r.component_id}
                            onChange={(e) =>
                              setRow(r.component_id, {
                                note: e.target.value,
                              })
                            }
                          />
                        </div>
                        <div className="lg-comp__act">
                          <button
                            type="button"
                            className="lg-btn-remove-comp"
                            title="Thôi trả khoản này cho người đó (kỳ đã chốt giữ nguyên số cũ)"
                            disabled={compBusy === r.component_id}
                            onClick={() => {
                              if (r.saved === null) {
                                void removeComp(r);
                              } else {
                                setConfirmDeleteComp(r);
                              }
                            }}
                          >
                            Gỡ
                          </button>
                        </div>
                      </div>
                    ))
                  )}

                  {/* Tổng phụ cấp danh mục tóm tắt ở chân bảng */}
                  {comps && comps.length > 0 && (
                    <div className="lg-comp-summary-strip">
                      <span>Tổng phụ cấp danh mục: <b>{money(compThu)} đ/tháng</b></span>
                      {compTru > 0 && (
                        <span className="lg-comp-summary-deduct"> · Khấu trừ: <b>-{money(compTru)} đ</b></span>
                      )}
                    </div>
                  )}
                </div>

                <div className="lg-comp__add">
                  {picking ? (
                    <div className="lg-add-comp-box">
                      <div className="lg-emp-select-wrap" style={{ minWidth: 260, flex: 1 }}>
                        <select
                          className="lg-emp-select"
                          autoFocus
                          aria-label="Chọn khoản thu nhập từ danh mục"
                          value=""
                          onChange={(e) => {
                            if (e.target.value) addComp(Number(e.target.value));
                          }}
                        >
                          <option value="">— Chọn khoản thu nhập trong danh mục —</option>
                          {addable.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.name} · {c.is_taxable ? "chịu thuế" : "miễn thuế"}
                              {c.kind === "tru" ? " · khấu trừ" : ""}
                            </option>
                          ))}
                        </select>
                        <ChevronDown size={14} className="lg-emp-select-chevron" />
                      </div>
                      <button
                        type="button"
                        className="btn btn--ghost"
                        onClick={() => setPicking(false)}
                      >
                        Hủy
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="btn btn--ghost lg-btn-add-comp"
                      disabled={catalog === null || addable.length === 0}
                      onClick={() => setPicking(true)}
                    >
                      <Plus size={14} />
                      <span>Thêm khoản từ danh mục</span>
                    </button>
                  )}
                  {catalogErr && (
                    <span className="cc-card__hint">
                      Không đọc được danh mục khoản thu nhập ({catalogErr}) —
                      chưa chọn thêm khoản được.
                    </span>
                  )}
                </div>
              </div>

              {/* Lương đợt 1 & % hoa hồng */}
              <div className="lg-form-card">
                <div className="lg-form-card__title">
                  Tạm ứng định kỳ &amp; Hoa hồng kinh doanh
                </div>
                <div className="ns-grid">
                  <label className="ns-field">
                    <span className="ns-field__label">
                      Lương trả 1 lần (đợt 1)
                    </span>
                    <input
                      type="number"
                      min={0}
                      step={100000}
                      value={luongDot1}
                      onChange={(e) => setLuongDot1(Number(e.target.value))}
                    />
                    <span className="cc-card__hint">
                      Mức trả trong MỘT lần, KHÔNG cộng vào lương tháng. Đây chỉ
                      là số điền sẵn khi lập phiếu tạm ứng đợt 1.
                    </span>
                  </label>
                  <label className="ns-field">
                    <span className="ns-field__label">
                      % hoa hồng (NV kinh doanh)
                    </span>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      step={0.5}
                      placeholder="0"
                      value={commissionPct || ""}
                      onChange={(e) =>
                        setCommissionPct(
                          e.target.value === "" ? 0 : Number(e.target.value),
                        )
                      }
                    />
                    <span className="cc-card__hint">
                      Bỏ trống / 0 nếu không phải nhân viên kinh doanh.
                    </span>
                  </label>
                </div>

                {/* Legacy allowance if > 0 */}
                {allowance > 0 && (
                  <div className="ns-field lg-legacy" style={{ marginTop: 12 }}>
                    <span className="ns-field__label">
                      Các khoản phụ cấp (số cũ, gộp một cục)
                    </span>
                    <input
                      type="number"
                      value={allowance}
                      readOnly
                      tabIndex={-1}
                      aria-label="Các khoản phụ cấp gộp một cục (số cũ, chỉ đọc)"
                    />
                    <span className="cc-card__hint">
                      Số cũ gộp một cục — nên tách ra từng khoản danh mục bên
                      trên.{" "}
                      <button
                        type="button"
                        className="lg-linkbtn"
                        onClick={() => setAllowance(0)}
                      >
                        Đưa về 0 sau khi đã tách
                      </button>
                    </span>
                  </div>
                )}

                {(phuCapCa > 0 || phuCapThamNien > 0) && (
                  <div className="ns-grid" style={{ marginTop: 12 }}>
                    {phuCapCa > 0 && (
                      <label className="ns-field">
                        <span className="ns-field__label">
                          Phụ cấp ca (đã ngưng)
                        </span>
                        <input
                          type="number"
                          value={phuCapCa}
                          readOnly
                          disabled
                        />
                        <span className="cc-card__hint">
                          Số cũ giữ lại để tra cứu lịch sử.
                        </span>
                      </label>
                    )}
                    {phuCapThamNien > 0 && (
                      <label className="ns-field">
                        <span className="ns-field__label">
                          Phụ cấp thâm niên (đã ngưng)
                        </span>
                        <input
                          type="number"
                          value={phuCapThamNien}
                          readOnly
                          disabled
                        />
                        <span className="cc-card__hint">
                          Số cũ giữ lại để tra cứu lịch sử.
                        </span>
                      </label>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Tab 2: Bảo hiểm & Công đoàn */}
          {activeTab === "insurance" && (
            <div className="lg-modal-tab-content">
              <div className="lg-form-card">
                <div className="lg-form-card__title">
                  Cấu hình mức đóng BHXH &amp; Công đoàn
                </div>
                <label className="ns-field" style={{ maxWidth: 360 }}>
                  <span className="ns-field__label">
                    {insuranceElsewhere
                      ? "Mức đóng BHXH"
                      : "Mức đóng BHXH *"}
                  </span>
                  <input
                    type="number"
                    min={0}
                    step={100000}
                    value={mucDongBh ?? 0}
                    disabled={insuranceElsewhere}
                    onChange={(e) => setMucDongBh(Number(e.target.value))}
                  />
                  <span className="cc-card__hint">
                    {insuranceElsewhere
                      ? "Người này đã có nơi khác đóng BHXH/BHYT/BHTN — công ty chỉ nộp TNLĐ-BNN, ô này để trống cũng được."
                      : "Số trên hợp đồng bảo hiểm của người này. Bắt buộc khai riêng từng người."}
                  </span>
                </label>

                <div style={{ marginTop: 14 }}>
                  <label className="ns-check">
                    <input
                      type="checkbox"
                      checked={insuranceElsewhere}
                      onChange={(e) => setInsuranceElsewhere(e.target.checked)}
                    />
                    <span>
                      Bảo hiểm đóng ở nơi khác — công ty chỉ đóng TNLĐ-BNN
                    </span>
                  </label>
                  <p
                    className="cc-card__hint"
                    style={{ marginLeft: 22, marginTop: 2 }}
                  >
                    Tích khi NV đã được nơi khác đóng BHXH/BHYT/BHTN. Công ty
                    không khấu trừ 3 khoản này của họ.
                  </p>

                  <label className="ns-check" style={{ marginTop: 10 }}>
                    <input
                      type="checkbox"
                      checked={unionMember}
                      onChange={(e) => setUnionMember(e.target.checked)}
                    />
                    <span>Đoàn viên công đoàn — có trừ đoàn phí công đoàn</span>
                  </label>
                  <p
                    className="cc-card__hint"
                    style={{ marginLeft: 22, marginTop: 2 }}
                  >
                    Chỉ đoàn viên mới bị trừ đoàn phí công đoàn (1% trên mức
                    nền). Không tích = không trừ.
                  </p>
                </div>
              </div>

              {/* Simulation card for insurance breakdown */}
              <div className="lg-form-card">
                <div className="lg-form-card__title">
                  Mô phỏng chi tiết đóng bảo hiểm hằng tháng
                </div>
                {isProbation ? (
                  <div className="banner banner--info" style={{ marginTop: 8 }}>
                    Nhân viên <b>thử việc</b> — chưa tham gia đóng BHXH/BHYT/BHTN
                    theo quy định hợp đồng thử việc.
                  </div>
                ) : insuranceElsewhere ? (
                  <div className="lg-sim-elsewhere">
                    <p className="cc-note">
                      Nhân viên có <b>BH đóng ở nơi khác</b>: Công ty không khấu
                      trừ BHXH/BHYT/BHTN vào lương của nhân viên.
                    </p>
                    <div className="lg-sim-row" style={{ marginTop: 8 }}>
                      <span>
                        TNLĐ-BNN công ty đóng ({pctOf(tnldBnnRate)}%):
                      </span>
                      <span className="lg-num font-bold">
                        <b>{money(bhBase * tnldBnnRate)} đ/tháng</b>
                      </span>
                    </div>
                    <p className="cc-card__hint" style={{ marginTop: 4 }}>
                      Chi phí TNLĐ-BNN do doanh nghiệp chịu hoàn toàn, không trừ
                      vào lương nhân viên.
                    </p>
                  </div>
                ) : (
                  <div className="lg-sim-container">
                    <p className="cc-card__hint" style={{ marginBottom: 12 }}>
                      Mức căn cứ đóng BH: <b>{money(bhBase)} đ</b>{" "}
                      {bhCapY < bhBase &&
                        `(áp trần BHXH/BHYT: ${money(bhCapY)} đ)`}
                    </p>
                    <div className="lg-sim-grid">
                      {/* Chi tiết Người lao động đóng */}
                      <div className="lg-sim-col">
                        <div className="lg-sim-col__head">
                          Người lao động đóng
                        </div>
                        <div className="lg-sim-row">
                          <span>BHXH ({pctOf(bhxhRate)}%)</span>
                          <span className="lg-num">{money(bhxhAmt)} đ</span>
                        </div>
                        <div className="lg-sim-row">
                          <span>BHYT ({pctOf(bhytRate)}%)</span>
                          <span className="lg-num">{money(bhytAmt)} đ</span>
                        </div>
                        <div className="lg-sim-row">
                          <span>BHTN ({pctOf(bhtnRate)}%)</span>
                          <span className="lg-num">{money(bhtnAmt)} đ</span>
                        </div>
                        {unionMember && (
                          <div className="lg-sim-row">
                            <span>Đoàn phí CĐ (1% nền)</span>
                            <span className="lg-num">
                              {money(unionFeeAmt)} đ
                            </span>
                          </div>
                        )}
                        <div className="lg-sim-row lg-sim-row--total">
                          <span>Tổng NLĐ đóng:</span>
                          <span className="lg-num lg-minus">
                            <b>
                              {money(
                                bhTotal + (unionMember ? unionFeeAmt : 0),
                              )}{" "}
                              đ/tháng
                            </b>
                          </span>
                        </div>
                      </div>

                      {/* Chi tiết Công ty đóng */}
                      <div className="lg-sim-col">
                        <div className="lg-sim-col__head">
                          Doanh nghiệp đóng
                        </div>
                        <div className="lg-sim-row">
                          <span>BHXH ({pctOf(bhxhErRate)}%)</span>
                          <span className="lg-num">{money(erBhxhAmt)} đ</span>
                        </div>
                        <div className="lg-sim-row">
                          <span>BHYT ({pctOf(bhytErRate)}%)</span>
                          <span className="lg-num">{money(erBhytAmt)} đ</span>
                        </div>
                        <div className="lg-sim-row">
                          <span>BHTN ({pctOf(bhtnErRate)}%)</span>
                          <span className="lg-num">{money(erBhtnAmt)} đ</span>
                        </div>
                        <div className="lg-sim-row">
                          <span>TNLĐ-BNN ({pctOf(tnldBnnRate)}%)</span>
                          <span className="lg-num">{money(erTnldAmt)} đ</span>
                        </div>
                        <div className="lg-sim-row lg-sim-row--total">
                          <span>Tổng Công ty đóng:</span>
                          <span className="lg-num lg-plus-val">
                            <b>{money(erTotal)} đ/tháng</b>
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="lg-sim-footer">
                      <span>
                        Tổng chi phí nhân sự tháng (Lương + BH doanh nghiệp):
                      </span>
                      <span className="lg-sim-grand-total">
                        <b>{money(sysThu + compThu + erTotal)} đ/tháng</b>
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Tab 3: Lịch sử điều chỉnh */}
          {activeTab === "history" && (
            <div className="lg-modal-tab-content">
              <div className="ns__tablewrap" style={{ overflowX: "auto" }}>
                <table className="ns__table">
                  <thead>
                    <tr>
                      <th>Trạng thái</th>
                      <th>Ngày hiệu lực</th>
                      <th className="lg-num">Mức nền</th>
                      <th className="lg-num">Phụ cấp</th>
                      <th>Người sửa &amp; thời gian</th>
                      <th>Ghi chú</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(history ?? []).map((s) => {
                      const vt = s.luong_vi_tri ?? 0;
                      const tn = s.luong_trach_nhiem ?? 0;
                      const nen =
                        vt + tn > 0 ? vt + tn : (s.base_amount ?? 0);
                      return (
                        <tr key={s.id}>
                          <td>
                            {s.is_current ? (
                              <span className="ns-badge ns-badge--ok">
                                Đang áp dụng
                              </span>
                            ) : s.effective_to == null ? (
                              <span className="ns-badge ns-badge--muted">
                                Sắp áp dụng
                              </span>
                            ) : (
                              <span className="ns-badge ns-badge--muted">
                                Đã thay
                              </span>
                            )}
                          </td>
                          <td>{fmtYmd(s.effective_from)}</td>
                          <td className="lg-num">
                            <b>{money(nen)} đ</b>
                          </td>
                          <td className="lg-num">{money(s.allowance)} đ</td>
                          <td>
                            <div>
                              <b>{s.actor_name ?? "—"}</b>
                            </div>
                            <div
                              className="cc-card__hint"
                              style={{ fontSize: 11 }}
                            >
                              {fmtDateTime(s.created_at)}
                            </div>
                          </td>
                          <td>{s.note ?? "—"}</td>
                        </tr>
                      );
                    })}
                    {(history ?? []).length === 0 && (
                      <EmptyRow
                        colSpan={6}
                        trangThai={
                          histErr
                            ? "loi"
                            : history === null
                              ? "dang-tai"
                              : "rong"
                        }
                        loi={histErr}
                        onThuLai={() => void reload()}
                        icon="clock"
                        title="Chưa khai lương cho người này"
                        sub="Điền các ô ở Tab “Mức lương & Phụ cấp” rồi bấm “Lưu điều chỉnh” — mốc đầu tiên sẽ nằm ở đây."
                      />
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* 4. Sticky Modal Footer */}
        <footer className="lg-modal-foot-sticky">
          <div className="lg-modal-foot-left">
            <span>
              Tổng thu nhập dự kiến:{" "}
              <b style={{ fontSize: 16, color: "#15803d", fontFamily: "var(--ff-num, inherit)" }}>
                {money(sysThu + compThu - compTru)} đ
              </b>
            </span>
          </div>
          <div className="lg-modal-foot-right">
            <button type="button" className="btn btn--ghost" onClick={onClose}>
              Hủy / Đóng
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={doSave}
              disabled={busy || history === null}
            >
              {busy ? "Đang lưu…" : "Lưu điều chỉnh"}
            </button>
          </div>
        </footer>
      </div>

      {/* Confirmation Dialog before removing a saved recurring component */}
      <ConfirmDialog
        open={!!confirmDeleteComp}
        title="Xác nhận gỡ khoản thu nhập"
        confirmLabel="Gỡ khoản này"
        danger
        busy={compBusy !== null}
        onCancel={() => setConfirmDeleteComp(null)}
        onConfirm={() => {
          if (confirmDeleteComp) {
            void removeComp(confirmDeleteComp);
            setConfirmDeleteComp(null);
          }
        }}
      >
        <p className="cdlg__msg">
          Bạn có chắc muốn gỡ khoản “<b>{confirmDeleteComp?.name}</b>” (
          {money(confirmDeleteComp?.draft)} đ) khỏi nhân viên{" "}
          <b>{emp.full_name}</b>?
        </p>
        <p className="cdlg__msg">
          Kỳ lương đã chốt giữ nguyên số cũ. Khoản này sẽ dừng trả từ kỳ tính
          tới.
        </p>
      </ConfirmDialog>
    </div>
  );
}
