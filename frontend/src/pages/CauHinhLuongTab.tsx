// Cấu hình lương — MỘT tab của màn Lương (không phải màn riêng), 2 tab con:
//   • Cơ chế lương theo bộ phận — 8 tham số toàn công ty + 4 thành phần lương của tổ.
//   • Bảo hiểm & Thuế          — bảo hiểm 2 phía + thuế TNCN.
//
// PRD v2.1: chuyên cần trừ dần khai theo TỔ · các khoản phụ cấp (ca · thâm niên · khác) KHÔNG
// còn ở màn này — khai TAY theo TỪNG NGƯỜI ở tab "Lương nhân viên", một số cố định dùng mọi
// tháng. Bảng đơn giá ca + danh mục phụ cấp công ty đã gỡ khỏi backend (endpoint 404).
// LUẬT LƯU (S1): sửa thẳng trên trang → gom vào THANH LƯU sticky dưới cùng, mỗi tab con đúng
// MỘT thanh.
// Quyền: `luong:view_salary` xem được; `luong:update` được xem và sửa. `luong:read` riêng lẻ
// không được xem dữ liệu cấu hình nhạy cảm.
import { useCallback, useEffect, useMemo, useState } from "react";
import { Info, Trash2 } from "lucide-react";
import {
  api,
  type Department,
  type DeptComponent,
  type LatePenaltyBracket,
  type PayrollParams,
  type PitBracket,
  type SalaryComponentKey,
} from "../api/client";
import { Button } from "../components/Button";
import { DiscardChangesDialog } from "../components/DiscardChangesDialog";
import { KhoanRatesEditor } from "../components/KhoanRatesEditor";
import { money } from "../utils/format";
import "./luong.css";
import "./rebuild-catalog.css";

// --- Hằng dùng chung --------------------------------------------------------

type SubTab = "cochE" | "phucap";

const SUB_TABS: { key: SubTab; label: string }[] = [
  { key: "cochE", label: "Cơ chế lương theo bộ phận" },
  { key: "phucap", label: "Bảo hiểm & Thuế" },
];

/** 4 thành phần lương khai theo BỘ PHẬN (PRD v2.1). Các khoản phụ cấp (ca · thâm niên) đã
 *  chuyển sang khai TAY ở từng NV — gửi key cũ lên `PUT /dept-components` giờ ăn 422. */
const COMPONENT_ROWS: {
  key: SalaryComponentKey;
  name: string;
  desc: string;
  /** "money" = có ô tiền · null = chỉ bật/tắt, không có ô giá trị. */
  kind: "money" | null;
  unit: string;
  /** Bật mà bỏ trống ô tiền ⇒ 0 đ (không có mức cấp công ty để rơi xuống). */
  zeroWhenBlank?: boolean;
}[] = [
  {
    key: "kpi",
    name: "Thưởng năng suất KPI",
    desc: "Mức TRẦN. Tiền thưởng = % đạt của từng người × mức trần này, nhập % ở modal “Sửa lương” của bảng lương tháng.",
    kind: "money",
    unit: "đ / tháng",
    zeroWhenBlank: true,
  },
  {
    key: "chuyen_can",
    name: "Chuyên cần",
    desc: "Công tắc bật/tắt cho cả tổ — TẮT thì không ai trong tổ được cộng, kể cả đã khai tiền. MỨC TIỀN khai ở hồ sơ từng nhân viên (tab Lương nhân viên). Trừ dần theo ngày nghỉ: nghỉ 0,5 ngày −25% · 1 ngày −50% · từ 2 ngày mất hết.",
    kind: null,
    unit: "—",
  },
  {
    key: "luong_khoan",
    name: "Lương khoán / sản lượng",
    desc: "Bật khoán sẽ TỰ TẮT Tăng ca (đã khoán không tính tăng ca theo giờ) và hiện mục khai ĐƠN GIÁ khoán của tổ ngay dưới. Tính tiền khoán theo sản lượng nối khi có Lệnh sản xuất.",
    kind: null,
    unit: "—",
  },
  {
    key: "tang_ca",
    name: "Tăng ca",
    desc: "Loại trừ với Lương khoán — bật Tăng ca thì khoán tự tắt. Bộ phận ăn khoán không tính tăng ca theo giờ.",
    kind: null,
    unit: "—",
  },
];

// --- Helper -----------------------------------------------------------------

function errText(e: unknown): string {
  return e instanceof Error ? e.message : "Có lỗi xảy ra.";
}
/** Hệ số nhân (1.5) → % hiển thị (150). Tránh 149.99999 do dấu phẩy động. */
function toPct(v: number): number {
  return Math.round(v * 1000) / 10;
}
/** Sắp phòng ban theo CÂY: phòng cha rồi tổ con ngay dưới (dải chip đọc theo mạch tổ chức). */
function orderByTree(list: Department[]): Department[] {
  const ids = new Set(list.map((d) => d.id));
  const byParent = new Map<number | null, Department[]>();
  for (const d of list) {
    const p = d.parent_id != null && ids.has(d.parent_id) ? d.parent_id : null;
    const bucket = byParent.get(p) ?? [];
    bucket.push(d);
    byParent.set(p, bucket);
  }
  const out: Department[] = [];
  const walk = (parent: number | null) => {
    for (const d of byParent.get(parent) ?? []) {
      out.push(d);
      walk(d.id);
    }
  };
  walk(null);
  return out.length === list.length ? out : list;
}

// --- Ô nhập số dùng chung (primitive .rc-* của màn danh mục) -----------------

function NumInput({
  value,
  onChange,
  suffix,
  step,
  min,
  max,
  disabled,
  placeholder,
  invalid,
}: {
  value: number | null;
  onChange: (v: number | null) => void;
  suffix?: string;
  step?: number;
  min?: number;
  max?: number;
  disabled?: boolean;
  placeholder?: string;
  invalid?: boolean;
}) {
  return (
    <div
      className={`rc-input-wrapper${disabled ? " rc-input-wrapper--ro" : ""}`}
    >
      <input
        className={`rc-input rc-input--num${invalid ? " rc-input--invalid" : ""}`}
        type="number"
        inputMode="decimal"
        step={step ?? 1}
        min={min}
        max={max}
        disabled={disabled}
        placeholder={placeholder}
        value={value == null ? "" : value}
        onChange={(e) =>
          onChange(e.target.value === "" ? null : Number(e.target.value))
        }
      />
      {suffix && <span className="rc-input-suffix">{suffix}</span>}
    </div>
  );
}

/** Ô số bắt buộc có giá trị (tham số công ty) — rỗng quy về 0, không đẩy null xuống payload. */
function ParamField({
  label,
  hint,
  warn,
  value,
  onChange,
  suffix,
  step,
  min,
  max,
  readOnly,
}: {
  label: string;
  hint?: string;
  warn?: string | null;
  value: number;
  onChange: (v: number) => void;
  suffix?: string;
  step?: number;
  min?: number;
  max?: number;
  readOnly?: boolean;
}) {
  return (
    <div className="rc-field">
      <span className="rc-field__label">{label}</span>
      <NumInput
        value={value}
        onChange={(v) => onChange(v ?? 0)}
        suffix={suffix}
        step={step}
        min={min}
        max={max}
        disabled={readOnly}
      />
      {warn ? (
        <span className="rc-field__hint cl-warn">{warn}</span>
      ) : hint ? (
        <span className="rc-field__hint">{hint}</span>
      ) : null}
    </div>
  );
}

function Switch({
  on,
  onChange,
  disabled,
  label,
}: {
  on: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <label className="rc-switch">
      <input
        type="checkbox"
        checked={on}
        disabled={disabled}
        aria-label={label}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="rc-switch__slider" />
    </label>
  );
}

// --- Kiểu state cục bộ ------------------------------------------------------

/** Một bậc thuế trong state cục bộ — `id: null` = bậc mới, chưa POST. */
type BracketDraft = {
  key: string;
  id: number | null;
  up_to: number | null;
  rate: number;
};
/** Một bậc PHẠT trễ/sớm trong state cục bộ — `id: null` = bậc mới, chưa POST. */
type PenaltyDraft = {
  key: string;
  id: number | null;
  up_to_minute: number | null;
  amount: number;
};
type PendingNav =
  | { kind: "dept"; id: number }
  | { kind: "sub"; sub: SubTab }
  | null;

const READONLY_NOTE =
  "Bạn chỉ có quyền XEM cấu hình lương. Cần sửa thì liên hệ quản trị hệ thống.";
const SAVED_NOTE =
  "Kỳ lương đang ở trạng thái nháp sẽ áp số mới khi bấm “Tính lại”. Kỳ đã chốt / đã chi giữ nguyên số.";

// ============================================================================

export function CauHinhLuongTab({
  token,
  readOnly,
  onDirtyChange,
}: {
  token: string;
  readOnly: boolean;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [sub, setSub] = useState<SubTab>("cochE");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // --- dữ liệu toàn công ty (tải 1 lần) ---
  const [depts, setDepts] = useState<Department[]>([]);
  const [params, setParams] = useState<PayrollParams | null>(null);
  const [paramsDraft, setParamsDraft] = useState<PayrollParams | null>(null);
  const [brackets, setBrackets] = useState<BracketDraft[]>([]);
  const [bracketsDraft, setBracketsDraft] = useState<BracketDraft[]>([]);
  const [penalties, setPenalties] = useState<PenaltyDraft[]>([]);
  const [penaltiesDraft, setPenaltiesDraft] = useState<PenaltyDraft[]>([]);

  // --- dữ liệu theo bộ phận đang chọn ---
  const [deptId, setDeptId] = useState<number | null>(null);
  const [compsLoading, setCompsLoading] = useState(false);
  const [comps, setComps] = useState<DeptComponent[]>([]);
  const [compsDraft, setCompsDraft] = useState<DeptComponent[]>([]);
  const [pendingNav, setPendingNav] = useState<PendingNav>(null);

  const dept = depts.find((d) => d.id === deptId) ?? null;
  const deptName = dept?.name ?? "";

  // --- tải lần đầu ---------------------------------------------------------
  const loadAll = useCallback(() => {
    setLoading(true);
    setErr(null);
    // Dải chip cần cây phòng ban + số NV; người chỉ có quyền `luong` mà không có
    // `phong_ban:read` thì lùi về danh mục phẳng của Nhân sự.
    const deptsP: Promise<Department[]> = api.rbac
      .departments(token)
      .catch(async () =>
        (await api.employees.meta(token)).departments.map(
          (d) => ({ id: d.id, name: d.name, code: "" }) as Department,
        ),
      )
      // Không có cả 2 quyền → vẫn mở được màn (khối toàn công ty), chỉ mất dải chip.
      .catch(() => []);
    Promise.all([
      deptsP,
      api.luong.getParams(token),
      api.luong.pitBrackets(token),
      api.luong.latePenaltyBrackets(token),
    ])
      .then(([ds, ps, bs, pens]) => {
        const ordered = orderByTree(ds);
        setDepts(ordered);
        setParams(ps);
        setParamsDraft(ps);
        const bd = as2Draft(bs.items);
        setBrackets(bd);
        setBracketsDraft(bd);
        const pd = as2PenaltyDraft(pens.items);
        setPenalties(pd);
        setPenaltiesDraft(pd);
        setDeptId((cur) => cur ?? ordered[0]?.id ?? null);
        setLoading(false);
      })
      .catch((e) => {
        setErr(errText(e));
        setLoading(false);
      });
  }, [token]);
  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // --- tải theo bộ phận ----------------------------------------------------
  const loadDept = useCallback(
    (id: number) => {
      setCompsLoading(true);
      api.luong
        .deptComponents(token, id)
        .then((cs) => {
          setComps(cs.items);
          setCompsDraft(cs.items);
          setCompsLoading(false);
        })
        .catch((e) => {
          setErr(errText(e));
          setCompsLoading(false);
        });
    },
    [token],
  );
  useEffect(() => {
    if (deptId != null) loadDept(deptId);
  }, [deptId, loadDept]);

  // --- cờ "chưa lưu" -------------------------------------------------------
  const dirtyA = useMemo(
    () =>
      !!params &&
      !!paramsDraft &&
      PARAMS_A.some((k) => params[k] !== paramsDraft[k]),
    [params, paramsDraft],
  );
  const dirtyIns = useMemo(
    () =>
      !!params &&
      !!paramsDraft &&
      PARAMS_INS.some((k) => params[k] !== paramsDraft[k]),
    [params, paramsDraft],
  );
  const dirtyTax = useMemo(
    () =>
      (!!params &&
        !!paramsDraft &&
        PARAMS_TAX.some((k) => params[k] !== paramsDraft[k])) ||
      JSON.stringify(brackets) !== JSON.stringify(bracketsDraft),
    [params, paramsDraft, brackets, bracketsDraft],
  );
  const dirtyComps = useMemo(
    () => JSON.stringify(comps) !== JSON.stringify(compsDraft),
    [comps, compsDraft],
  );
  const dirtyPenalty = useMemo(
    () => JSON.stringify(penalties) !== JSON.stringify(penaltiesDraft),
    [penalties, penaltiesDraft],
  );
  const bracketErrors = useMemo(
    () => validateBrackets(bracketsDraft),
    [bracketsDraft],
  );
  const penaltyErrors = useMemo(
    () => validatePenalties(penaltiesDraft),
    [penaltiesDraft],
  );
  const tabDirty: Record<SubTab, boolean> = {
    cochE: dirtyA || dirtyComps,
    phucap: dirtyIns || dirtyTax || dirtyPenalty,
  };
  const anyDirty = tabDirty.cochE || tabDirty.phucap;

  useEffect(() => {
    onDirtyChange?.(anyDirty);
  }, [anyDirty, onDirtyChange]);

  // Rời hẳn màn / F5 khi đang dirty → trình duyệt hỏi lại.
  useEffect(() => {
    if (!anyDirty) return;
    const h = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [anyDirty]);

  // --- điều hướng có bảo vệ ------------------------------------------------
  function askDept(id: number) {
    if (id === deptId) return;
    // Chỉ khối THUỘC bộ phận (cơ chế lương) mới cần hỏi; khối toàn công ty không liên quan.
    if (dirtyComps) setPendingNav({ kind: "dept", id });
    else setDeptId(id);
  }
  function askSub(next: SubTab) {
    if (next === sub) return;
    if (tabDirty[sub]) setPendingNav({ kind: "sub", sub: next });
    else setSub(next);
  }
  function discardPending() {
    if (!pendingNav) return;
    if (pendingNav.kind === "dept") {
      setCompsDraft(comps);
      setDeptId(pendingNav.id);
    } else {
      revertTab(sub);
      setSub(pendingNav.sub);
    }
    setPendingNav(null);
  }
  function revertTab(which: SubTab) {
    if (which === "cochE") {
      setCompsDraft(comps);
      if (params) setParamsDraft((d) => (d ? restore(d, params, PARAMS_A) : d));
    } else if (which === "phucap") {
      setBracketsDraft(brackets);
      setPenaltiesDraft(penalties);
      if (params)
        setParamsDraft((d) =>
          d ? restore(restore(d, params, PARAMS_INS), params, PARAMS_TAX) : d,
        );
    }
  }

  function flashSaved() {
    setOk("Đã lưu cấu hình.");
    setTimeout(() => setOk(null), 4000);
  }
  /** Sửa MỘT tham số công ty (key động) — giữ nguyên kiểu, không cast object rời. */
  const setParamKey = useCallback((key: keyof PayrollParams, value: number) => {
    setParamsDraft((d) => (d ? { ...d, [key]: value } : d));
  }, []);

  // --- lưu theo tab --------------------------------------------------------
  async function saveTab() {
    if (!paramsDraft || saving) return;
    setSaving(true);
    setErr(null);
    const failed: string[] = [];
    try {
      if (sub === "cochE") {
        if (dirtyA) {
          try {
            setParams(
              await api.luong.updateParams(token, pick(paramsDraft, PARAMS_A)),
            );
          } catch (e) {
            failed.push(`Tham số công ty (${errText(e)})`);
          }
        }
        if (dirtyComps && deptId != null) {
          try {
            const res = await api.luong.setDeptComponents(
              token,
              deptId,
              compsDraft.map((c) => ({
                component_key: c.component_key,
                is_enabled: c.is_enabled,
                value: c.value,
              })),
            );
            setComps(res.items);
            setCompsDraft(res.items);
          } catch (e) {
            failed.push(`Cơ chế bộ phận ${deptName} (${errText(e)})`);
          }
        }
      } else if (sub === "phucap") {
        if (dirtyIns) {
          try {
            setParams(
              await api.luong.updateParams(
                token,
                pick(paramsDraft, PARAMS_INS),
              ),
            );
          } catch (e) {
            failed.push(`Bảo hiểm bắt buộc (${errText(e)})`);
          }
        }
        if (dirtyTax) {
          try {
            await api.luong.updateParams(token, pick(paramsDraft, PARAMS_TAX));
            await saveBrackets();
            setParams(await api.luong.getParams(token));
          } catch (e) {
            failed.push(`Thuế TNCN (${errText(e)})`);
          }
        }
        if (dirtyPenalty) {
          try {
            await savePenalties();
          } catch (e) {
            failed.push(`Phạt đi trễ / về sớm (${errText(e)})`);
          }
        }
      }
    } finally {
      setSaving(false);
    }
    if (failed.length) setErr(`Chưa ghi được: ${failed.join(" · ")}`);
    else flashSaved();
  }

  /** Biểu thuế: xóa bậc đã bỏ → ghi/đè phần còn lại → tải lại (1 lần bấm, có try/catch ở trên). */
  async function saveBrackets() {
    const keptIds = new Set(
      bracketsDraft.map((b) => b.id).filter((x): x is number => x != null),
    );
    for (const b of brackets)
      if (b.id != null && !keptIds.has(b.id))
        await api.luong.deletePitBracket(token, b.id);
    for (let i = 0; i < bracketsDraft.length; i += 1) {
      const b = bracketsDraft[i];
      const body = { seq: i + 1, up_to: b.up_to, rate: b.rate };
      if (b.id == null) await api.luong.createPitBracket(token, body);
      else await api.luong.updatePitBracket(token, b.id, body);
    }
    const fresh = as2Draft((await api.luong.pitBrackets(token)).items);
    setBrackets(fresh);
    setBracketsDraft(fresh);
  }

  /** Bảng phạt: xóa bậc đã bỏ → ghi/đè phần còn lại → tải lại (mirror saveBrackets). */
  async function savePenalties() {
    const keptIds = new Set(
      penaltiesDraft.map((b) => b.id).filter((x): x is number => x != null),
    );
    for (const b of penalties)
      if (b.id != null && !keptIds.has(b.id))
        await api.luong.deleteLatePenaltyBracket(token, b.id);
    for (let i = 0; i < penaltiesDraft.length; i += 1) {
      const b = penaltiesDraft[i];
      const body = {
        seq: i + 1,
        up_to_minute: b.up_to_minute,
        amount: b.amount,
      };
      if (b.id == null) await api.luong.createLatePenaltyBracket(token, body);
      else await api.luong.updateLatePenaltyBracket(token, b.id, body);
    }
    const fresh = as2PenaltyDraft(
      (await api.luong.latePenaltyBrackets(token)).items,
    );
    setPenalties(fresh);
    setPenaltiesDraft(fresh);
  }

  // --- render --------------------------------------------------------------
  if (loading)
    return (
      <div className="cl">
        <p className="depts__status">Đang tải cấu hình…</p>
      </div>
    );
  if (err && !params)
    return (
      <div className="cl">
        <div className="banner banner--error">
          <span>Không tải được cấu hình lương.</span>
          <button className="btn btn--ghost" onClick={loadAll}>
            Thử lại
          </button>
        </div>
      </div>
    );

  const dirtyNames: string[] = [];
  if (sub === "cochE") {
    if (dirtyA) dirtyNames.push("Tham số công ty");
    if (dirtyComps) dirtyNames.push(`Cơ chế bộ phận ${deptName}`);
  } else if (sub === "phucap") {
    if (dirtyIns) dirtyNames.push("Bảo hiểm bắt buộc");
    if (dirtyTax) dirtyNames.push("Thuế TNCN");
    if (dirtyPenalty) dirtyNames.push("Phạt đi trễ / về sớm");
  }
  const blockedCount =
    sub === "phucap" ? bracketErrors.size + penaltyErrors.size : 0;
  const blocked = blockedCount > 0;

  return (
    <div className="cl">
      <nav className="cl-subtabs">
        {SUB_TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`cl-subtab${sub === t.key ? " is-active" : ""}`}
            onClick={() => askSub(t.key)}
          >
            {t.label}
            {tabDirty[t.key] && (
              <span className="cl-subtab__dot" aria-label="Chưa lưu" />
            )}
          </button>
        ))}
      </nav>

      {readOnly && <div className="banner banner--warn">{READONLY_NOTE}</div>}
      {err && params && <div className="banner banner--error">{err}</div>}
      {ok && (
        <div className="banner banner--success">
          <span>
            {ok}
            <span className="cl-banner-sub">{SAVED_NOTE}</span>
          </span>
        </div>
      )}

      {sub === "cochE" && paramsDraft && (
        <CoCheTab
          token={token}
          p={paramsDraft}
          setP={setParamKey}
          depts={depts}
          deptId={deptId}
          onPickDept={askDept}
          comps={compsDraft}
          setComps={setCompsDraft}
          loading={compsLoading}
          readOnly={readOnly}
          busy={saving}
        />
      )}

      {sub === "phucap" && paramsDraft && (
        <PhuCapTab
          p={paramsDraft}
          setP={setParamKey}
          brackets={bracketsDraft}
          setBrackets={setBracketsDraft}
          bracketErrors={bracketErrors}
          penalties={penaltiesDraft}
          setPenalties={setPenaltiesDraft}
          penaltyErrors={penaltyErrors}
          readOnly={readOnly}
          busy={saving}
        />
      )}

      {!readOnly && dirtyNames.length > 0 && (
        <div className="cl-savebar">
          <span className={`cl-savebar__txt${blocked ? " is-blocked" : ""}`}>
            {blocked
              ? `Còn ${blockedCount} ô sai — sửa xong mới lưu được.`
              : `Chưa lưu: ${dirtyNames.join(" · ")}`}
          </span>
          <span className="cl-savebar__acts">
            <Button
              variant="ghost"
              disabled={saving}
              onClick={() => revertTab(sub)}
            >
              Hủy thay đổi
            </Button>
            <Button
              variant="primary"
              loading={saving}
              disabled={blocked}
              onClick={saveTab}
            >
              Lưu thay đổi
            </Button>
          </span>
        </div>
      )}

      <DiscardChangesDialog
        open={pendingNav !== null}
        message={`Bạn có thay đổi chưa lưu ở ${dirtyNames.join(" · ") || "khối đang sửa"}. Rời đi mà không lưu?`}
        onDiscard={discardPending}
        onKeepEditing={() => setPendingNav(null)}
      />
    </div>
  );
}

// --- nhóm tham số theo KHỐI LƯU (thanh lưu chỉ ghi đúng khối của tab đang mở) ---
const PARAMS_A = [
  "standard_hours_per_day",
  "probation_ratio",
  "ot_multiplier",
  "ot_multiplier_restday",
  "ot_multiplier_holiday",
  "restday_work_multiplier",
  "holiday_work_multiplier",
  "night_pct",
  "ot_night_extra_pct",
  "adjust_max_per_month",
] as const satisfies readonly (keyof PayrollParams)[];
const PARAMS_INS = [
  "bhxh_rate",
  "bhyt_rate",
  "bhtn_rate",
  "bhxh_rate_er",
  "bhyt_rate_er",
  "bhtn_rate_er",
  "bh_base_cap",
  "bhtn_base_cap",
  "cong_doan_rate",
  "tnld_bnn_rate",
] as const satisfies readonly (keyof PayrollParams)[];
const PARAMS_TAX = [
  "deduction_self",
  "deduction_dependent",
] as const satisfies readonly (keyof PayrollParams)[];

function pick(
  p: PayrollParams,
  keys: readonly (keyof PayrollParams)[],
): Partial<PayrollParams> {
  const out: Partial<PayrollParams> = {};
  for (const k of keys) out[k] = p[k];
  return out;
}
function restore(
  draft: PayrollParams,
  base: PayrollParams,
  keys: readonly (keyof PayrollParams)[],
): PayrollParams {
  const out = { ...draft };
  for (const k of keys) out[k] = base[k];
  return out;
}
function as2Draft(items: PitBracket[]): BracketDraft[] {
  return items
    .slice()
    .sort((a, b) => a.seq - b.seq)
    .map((b) => ({ key: `b${b.id}`, id: b.id, up_to: b.up_to, rate: b.rate }));
}
/** Chỉ số dòng đang sai → tô đỏ + chặn nút Lưu. */
function validateBrackets(list: BracketDraft[]): Set<number> {
  const bad = new Set<number>();
  let prev = -1;
  list.forEach((b, i) => {
    if (b.rate < 0 || b.rate > 1) bad.add(i);
    if (b.up_to == null) {
      if (i !== list.length - 1) bad.add(i); // chỉ bậc CUỐI được để trống (∞)
      return;
    }
    if (b.up_to <= prev) bad.add(i);
    prev = b.up_to;
  });
  return bad;
}
function as2PenaltyDraft(items: LatePenaltyBracket[]): PenaltyDraft[] {
  return items
    .slice()
    .sort((a, b) => a.seq - b.seq)
    .map((b) => ({
      key: `p${b.id}`,
      id: b.id,
      up_to_minute: b.up_to_minute,
      amount: b.amount,
    }));
}
/** Validate bảng phạt: phút TĂNG DẦN · chỉ bậc CUỐI để trống (∞) · tiền ≥ 0. */
function validatePenalties(list: PenaltyDraft[]): Set<number> {
  const bad = new Set<number>();
  let prev = -1;
  list.forEach((b, i) => {
    if (b.amount < 0) bad.add(i);
    if (b.up_to_minute == null) {
      if (i !== list.length - 1) bad.add(i); // chỉ bậc CUỐI được để trống (∞)
      return;
    }
    if (b.up_to_minute <= prev) bad.add(i);
    prev = b.up_to_minute;
  });
  return bad;
}

// --- Dải chip phòng ban (dùng chung cho các tab) ----------------------------

function DeptChips({
  depts,
  deptId,
  counts,
  alert,
  disabled,
  onPick,
}: {
  depts: Department[];
  deptId: number | null;
  counts: Record<number, number>;
  /** true = số 0 tô rust. */
  alert: boolean;
  disabled?: boolean;
  onPick: (id: number) => void;
}) {
  if (!depts.length)
    return (
      <p className="cl-hint-inline">
        Chưa có phòng ban nào. Khai ở màn Phòng ban trước.
      </p>
    );
  const nameOf = (id?: number | null) =>
    depts.find((d) => d.id === id)?.name ?? null;
  return (
    <div className="cl-chips">
      {depts.map((d) => {
        const parent = nameOf(d.parent_id);
        const n = counts[d.id] ?? 0;
        return (
          <button
            key={d.id}
            type="button"
            className={`seg${d.id === deptId ? " is-active" : ""}`}
            disabled={disabled}
            title={parent ? `${parent} · ${d.name}` : d.name}
            onClick={() => onPick(d.id)}
          >
            {parent && <span className="cl-chip__parent">{parent} · </span>}
            {d.name}
            <span
              className={`chip-count${alert && n === 0 ? " chip-count--alert" : ""}`}
            >
              {n}
            </span>
          </button>
        );
      })}
    </div>
  );
}

// ============================================================================
// TAB 2 — Cơ chế lương theo bộ phận
// ============================================================================

function CoCheTab({
  token,
  p,
  setP,
  depts,
  deptId,
  onPickDept,
  comps,
  setComps,
  loading,
  readOnly,
  busy,
}: {
  token: string;
  p: PayrollParams;
  setP: (key: keyof PayrollParams, value: number) => void;
  depts: Department[];
  deptId: number | null;
  onPickDept: (id: number) => void;
  comps: DeptComponent[];
  setComps: (f: (c: DeptComponent[]) => DeptComponent[]) => void;
  loading: boolean;
  readOnly: boolean;
  busy: boolean;
}) {
  const deptName = depts.find((d) => d.id === deptId)?.name ?? "";
  const empCounts = useMemo(() => {
    const m: Record<number, number> = {};
    for (const d of depts) m[d.id] = d.employee_count ?? 0;
    return m;
  }, [depts]);

  const patchComp = (key: SalaryComponentKey, patch: Partial<DeptComponent>) =>
    setComps((cs) =>
      cs.map((c) => {
        if (c.component_key === key) return { ...c, ...patch };
        // Khoán ⟷ Tăng ca loại trừ nhau: bật cái này thì tự tắt cái kia.
        if (
          patch.is_enabled === true &&
          ((key === "luong_khoan" && c.component_key === "tang_ca") ||
            (key === "tang_ca" && c.component_key === "luong_khoan"))
        ) {
          return { ...c, is_enabled: false };
        }
        return c;
      }),
    );
  const khoanOn =
    comps.find((c) => c.component_key === "luong_khoan")?.is_enabled ?? false;

  return (
    <>
      <div className="cl-card">
        <h3 className="cl-card__title">Áp dụng toàn công ty</h3>
        <p className="cl-card__desc">
          Tham số nền cho mọi bộ phận. Bộ phận nào cần khác thì ghi đè ở khối
          dưới.
        </p>
        <div className="cl-card__body">
          <section className="rc-sec">
            <div className="rc-sec__title">Công chuẩn</div>
            <div className="cl-override-note">
              <Info size={14} />
              <span>
                <b>Công chuẩn / tháng</b> tự tính theo Chấm công →{" "}
                <b>Lịch &amp; Ngày lễ</b> (tuần làm việc − ngày lễ + làm bù)
                {/* nên mỗi tháng một khác — không khai tay ở đây nữa. */}
              </span>
            </div>
            <div className="rc-grid">
              <ParamField
                label="Giờ công chuẩn / ngày"
                hint="Dùng để quy ra đơn giá 1 giờ tăng ca."
                suffix="h"
                step={0.5}
                min={1}
                max={24}
                readOnly={readOnly}
                value={p.standard_hours_per_day}
                onChange={(v) => setP("standard_hours_per_day", v)}
              />
              <ParamField
                label="% lương thử việc"
                hint="Nhân vào mức nền của người đang thử việc."
                warn={
                  p.probation_ratio < 0.85
                    ? "Điều 26 BLLĐ tối thiểu 85% — vẫn lưu được, nhưng nên rà lại."
                    : null
                }
                suffix="%"
                min={1}
                max={100}
                readOnly={readOnly}
                value={toPct(p.probation_ratio)}
                onChange={(v) => setP("probation_ratio", v / 100)}
              />
              <ParamField
                label="Hạn mức chỉnh công / tháng"
                hint="Số NGÀY CÔNG mỗi người được tự xin chỉnh trong 1 tháng. Đếm theo ngày, không theo số đơn — quên cả giờ vào lẫn giờ ra của cùng một ngày vẫn là 1 lần. Đơn bị từ chối/hủy trả lại lượt. HCNS chấm bù trực tiếp KHÔNG bị giới hạn. 0 = không giới hạn."
                suffix="ngày"
                step={1}
                min={0}
                max={31}
                readOnly={readOnly}
                value={p.adjust_max_per_month}
                onChange={(v) => setP("adjust_max_per_month", Math.round(v))}
              />
            </div>
          </section>
          <section className="rc-sec">
            <div className="rc-sec__title">
              Hệ số làm thêm &amp; ngày đặc biệt
            </div>
            <div className="rc-grid">
              {OT_FIELDS.map((f) => (
                <ParamField
                  key={f.key}
                  label={f.label}
                  hint={f.hint}
                  warn={
                    p[f.key] < f.floor
                      ? `Thấp hơn mức tối thiểu Điều 98 BLLĐ (${f.floor * 100}%) — vẫn lưu được, nhưng nên rà lại.`
                      : null
                  }
                  suffix="%"
                  step={10}
                  min={100}
                  max={500}
                  readOnly={readOnly}
                  value={toPct(p[f.key])}
                  onChange={(v) => setP(f.key, v / 100)}
                />
              ))}
              <ParamField
                label="Phụ cấp làm ban đêm"
                hint="Cộng thêm cho giờ làm 22h–06h (≥30% theo luật). Giờ đêm TRONG ca theo lịch dùng hệ số riêng khai trên form Khai ca."
                suffix="%"
                step={5}
                min={0}
                max={200}
                readOnly={readOnly}
                value={toPct(p.night_pct)}
                onChange={(v) => setP("night_pct", v / 100)}
              />
              <ParamField
                label="Phụ cấp tăng ca đêm"
                hint="Cộng THÊM cho giờ TĂNG CA rơi 22h–06h (Điều 98.3, mặc định +20%). Vd tăng ca đêm ngày thường = 150% + 30% + 20% = 200%."
                suffix="%"
                step={5}
                min={0}
                max={200}
                readOnly={readOnly}
                value={toPct(p.ot_night_extra_pct)}
                onChange={(v) => setP("ot_night_extra_pct", v / 100)}
              />
            </div>
          </section>
        </div>
      </div>

      <DeptChips
        depts={depts}
        deptId={deptId}
        counts={empCounts}
        alert={false}
        disabled={busy}
        onPick={onPickDept}
      />

      <div className="cl-card">
        <h3 className="cl-card__title">Cơ chế lương — {deptName}</h3>
        <p className="cl-card__desc">
          Bật thành phần nào thì bộ phận này được tính thành phần đó. Công ty
          không đặt mức chung — khoản nào bật mà chưa khai mức tiền thì tính 0
          đ.
        </p>
        <div className="cl-card__body">
          <div className="cl-override-note">
            <Info size={14} />
            <span>
              <b>Chuyên cần</b>: tổ chỉ bật/tắt — mức tiền khai ở{" "}
              <b>hồ sơ từng nhân viên</b>, chưa khai thì 0 đ. <b>KPI</b>: bật mà
              bỏ trống ô tiền = 0 đ.
            </span>
          </div>
          {loading ? (
            <div className="cl-comp">
              {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
                <div className="cl-comp__row" key={`sk-${i}`}>
                  <span className="rc-skel" style={{ width: "36px" }} />
                  <span className="rc-skel" style={{ width: "60%" }} />
                  <span className="rc-skel" style={{ width: "80%" }} />
                  <span className="rc-skel" style={{ width: "40%" }} />
                  <span className="rc-skel" style={{ width: "60%" }} />
                </div>
              ))}
            </div>
          ) : (
            <div className="cl-comp">
              {COMPONENT_ROWS.map((def) => {
                const c = comps.find((x) => x.component_key === def.key);
                if (!c) return null;
                const off = !c.is_enabled;
                // C6: KHÔNG còn mức mặc định công ty để rơi xuống — bật mà bỏ trống là 0 đ.
                const blankZero =
                  def.zeroWhenBlank && c.is_enabled && c.value == null;
                return (
                  <div
                    className={`cl-comp__row${off ? " is-off" : ""}`}
                    key={def.key}
                  >
                    <span>
                      <Switch
                        on={c.is_enabled}
                        disabled={readOnly || busy}
                        label={def.name}
                        onChange={(v) => patchComp(def.key, { is_enabled: v })}
                      />
                    </span>
                    <span>
                      <span className="cl-comp__name">{def.name}</span>
                      <span className="cl-comp__desc">{def.desc}</span>
                    </span>
                    <span>
                      {def.kind ? (
                        <NumInput
                          value={c.value}
                          disabled={readOnly || off || busy}
                          suffix="đ"
                          step={100000}
                          min={0}
                          placeholder="0"
                          onChange={(v) => patchComp(def.key, { value: v })}
                        />
                      ) : null}
                    </span>
                    <span className="cl-comp__unit">{def.unit}</span>
                    <span className="cl-comp__src">
                      {blankZero && (
                        <span className="badge-sem badge-sem--amber">
                          Chưa khai mức = 0 đ
                        </span>
                      )}
                      {!c.company_enabled && (
                        <span className="badge-sem badge-sem--muted">
                          Công ty đang tắt
                        </span>
                      )}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {khoanOn && deptId != null && (
        <div className="cl-card">
          <h3 className="cl-card__title">Đơn giá khoán — {deptName}</h3>
          <p className="cl-card__desc">
            Khai công việc + đơn giá khoán của tổ này (vd “dán bìa các tông” =
            170đ/tờ). Tính tiền khoán theo sản lượng sẽ nối khi có Lệnh sản
            xuất.
          </p>
          <div className="cl-card__body">
            <KhoanRatesEditor
              token={token}
              departmentId={deptId}
              deptName={deptName}
            />
          </div>
        </div>
      )}
    </>
  );
}

/** 5 hệ số làm thêm / làm nguyên công — nhập & hiện bằng %, lưu DB vẫn là 1.5 / 2 / 3. */
const OT_FIELDS: {
  key:
    | "ot_multiplier"
    | "ot_multiplier_restday"
    | "ot_multiplier_holiday"
    | "restday_work_multiplier"
    | "holiday_work_multiplier";
  label: string;
  hint: string;
  floor: number;
}[] = [
  {
    key: "ot_multiplier",
    label: "Tăng ca — ngày thường",
    hint: "Trả theo giờ, trên đơn giá giờ của mức nền.",
    floor: 1.5,
  },
  {
    key: "ot_multiplier_restday",
    label: "Tăng ca — ngày nghỉ tuần",
    hint: "Giờ tăng ca rơi vào ngày nghỉ tuần.",
    floor: 2,
  },
  {
    key: "ot_multiplier_holiday",
    label: "Tăng ca — ngày lễ",
    hint: "Giờ tăng ca rơi vào ngày lễ / Tết.",
    floor: 3,
  },
  {
    key: "restday_work_multiplier",
    label: "Làm nguyên công — ngày nghỉ tuần",
    hint: "Đi làm trọn công vào ngày nghỉ tuần: cộng THÊM phần chênh (hệ số − 100%) vì 100% đã nằm trong lương theo công.",
    floor: 2,
  },
  {
    key: "holiday_work_multiplier",
    label: "Làm nguyên công — ngày lễ",
    hint: "Đi làm trọn công ngày lễ: cộng THÊM phần chênh (hệ số − 100%).",
    floor: 3,
  },
];

// ============================================================================
// TAB 3 — Bảo hiểm & Thuế
// ============================================================================

function PhuCapTab({
  p,
  setP,
  brackets,
  setBrackets,
  bracketErrors,
  penalties,
  setPenalties,
  penaltyErrors,
  readOnly,
  busy,
}: {
  p: PayrollParams;
  setP: (key: keyof PayrollParams, value: number) => void;
  brackets: BracketDraft[];
  setBrackets: (f: (b: BracketDraft[]) => BracketDraft[]) => void;
  bracketErrors: Set<number>;
  penalties: PenaltyDraft[];
  setPenalties: (f: (b: PenaltyDraft[]) => PenaltyDraft[]) => void;
  penaltyErrors: Set<number>;
  readOnly: boolean;
  busy: boolean;
}) {
  const totalEr = p.bhxh_rate_er + p.bhyt_rate_er + p.bhtn_rate_er;
  const totalEe = p.bhxh_rate + p.bhyt_rate + p.bhtn_rate;

  function addPenalty() {
    setPenalties((bs) => {
      // Gợi ý rule-based: mốc phút bậc mới = mốc kế cuối + 30; tiền = tiền bậc cuối.
      const withCap = bs.filter((b) => b.up_to_minute != null);
      const lastCap = withCap.length
        ? (withCap[withCap.length - 1].up_to_minute as number)
        : 0;
      const amount = bs.length ? bs[bs.length - 1].amount : 20000;
      const row: PenaltyDraft = {
        key: `n${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        id: null,
        up_to_minute: lastCap + 30,
        amount,
      };
      // Bậc ∞ (up_to_minute rỗng) luôn phải đứng CUỐI → chèn bậc mới ngay trước nó.
      const tailInfinite =
        bs.length > 0 && bs[bs.length - 1].up_to_minute == null;
      return tailInfinite
        ? [...bs.slice(0, -1), row, bs[bs.length - 1]]
        : [...bs, row];
    });
  }

  function addBracket() {
    setBrackets((bs) => {
      // Gợi ý rule-based: mức của bậc mới = mức bậc kế cuối × 1,5; thuế suất giữ của bậc cuối.
      const withCap = bs.filter((b) => b.up_to != null);
      const lastCap = withCap.length
        ? (withCap[withCap.length - 1].up_to as number)
        : 5_000_000;
      const rate = bs.length ? bs[bs.length - 1].rate : 0.05;
      const row: BracketDraft = {
        key: `n${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        id: null,
        up_to: Math.round(lastCap * 1.5),
        rate,
      };
      // Bậc ∞ (up_to rỗng) luôn phải đứng CUỐI → chèn bậc mới ngay trước nó.
      const tailInfinite = bs.length > 0 && bs[bs.length - 1].up_to == null;
      return tailInfinite
        ? [...bs.slice(0, -1), row, bs[bs.length - 1]]
        : [...bs, row];
    });
  }

  return (
    <>
      <div className="cl-override-note">
        <Info size={14} />
        <span>
          Bốn khoản phụ cấp (ca · trách nhiệm · thâm niên · khác) KHÔNG khai ở
          đây — gõ tay theo TỪNG NGƯỜI ở tab “Lương nhân viên”, một số cố định
          dùng cho mọi tháng.
        </span>
      </div>

      <div className="cl-card">
        <h3 className="cl-card__title">Bảo hiểm bắt buộc</h3>
        <div className="cl-card__body">
          <table className="cl-ins">
            <thead>
              <tr>
                <th>Khoản</th>
                <th className="num">NSDLĐ (%)</th>
                <th className="num">NLĐ (%)</th>
              </tr>
            </thead>
            <tbody>
              {INSURANCE_ROWS.map((r) => (
                <tr key={r.label}>
                  <td>{r.label}</td>
                  <td className="num">
                    <NumInput
                      value={toPct(p[r.er])}
                      disabled={readOnly || busy}
                      suffix="%"
                      step={0.5}
                      min={0}
                      max={100}
                      onChange={(v) => setP(r.er, (v ?? 0) / 100)}
                    />
                  </td>
                  <td className="num">
                    <NumInput
                      value={toPct(p[r.ee])}
                      disabled={readOnly || busy}
                      suffix="%"
                      step={0.5}
                      min={0}
                      max={100}
                      onChange={(v) => setP(r.ee, (v ?? 0) / 100)}
                    />
                  </td>
                </tr>
              ))}
              <tr className="cl-ins__total">
                <td>Tổng</td>
                <td className="num">{toPct(totalEr)}%</td>
                <td className="num">{toPct(totalEe)}%</td>
              </tr>
            </tbody>
          </table>
          <p className="cl-hint-inline">
            Cột NSDLĐ KHÔNG trừ vào lương nhân viên — chỉ dùng để tính chi phí
            bảo hiểm của công ty và tổng quỹ lương.
          </p>
          <p className="cl-hint-inline">
            Nhân viên thử việc chưa đóng bảo hiểm.
          </p>
          <section className="rc-sec">
            <div className="rc-grid">
              <ParamField
                label="Trần đóng BHXH + BHYT"
                hint="Phần lương vượt trần không tính đóng BHXH và BHYT."
                suffix="đ"
                step={100000}
                min={0}
                readOnly={readOnly}
                value={p.bh_base_cap}
                onChange={(v) => setP("bh_base_cap", v)}
              />
              <ParamField
                label="Trần đóng BHTN"
                hint="Trần riêng của BHTN, khác trần BHXH/BHYT."
                suffix="đ"
                step={100000}
                min={0}
                readOnly={readOnly}
                value={p.bhtn_base_cap}
                onChange={(v) => setP("bhtn_base_cap", v)}
              />
              <ParamField
                label="Đoàn phí công đoàn (NV đóng)"
                hint="Trừ vào thực nhận, KHÔNG giảm thu nhập chịu thuế TNCN."
                suffix="%"
                step={0.5}
                min={0}
                max={100}
                readOnly={readOnly}
                value={toPct(p.cong_doan_rate)}
                onChange={(v) => setP("cong_doan_rate", v / 100)}
              />
              <ParamField
                label="TNLĐ-BNN (công ty đóng)"
                hint="Tai nạn LĐ – Bệnh nghề nghiệp. Dùng khi NV có BH đóng ở nơi khác — công ty chỉ chịu khoản này. KHÔNG trừ vào lương NV."
                suffix="%"
                step={0.1}
                min={0}
                max={100}
                readOnly={readOnly}
                value={toPct(p.tnld_bnn_rate)}
                onChange={(v) => setP("tnld_bnn_rate", v / 100)}
              />
            </div>
          </section>
        </div>
      </div>

      <div className="cl-card">
        <h3 className="cl-card__title">Thuế thu nhập cá nhân</h3>
        <p className="cl-card__desc">
          Thu nhập tính thuế = thu nhập chịu thuế − bảo hiểm − giảm trừ gia
          cảnh. Biểu lũy tiến từng phần, tính theo tháng. Sửa khi luật đổi (mặc
          định 2026: Luật 109/2025).
        </p>
        <div className="cl-card__body">
          <section className="rc-sec">
            <div className="rc-grid">
              <ParamField
                label="Giảm trừ bản thân"
                hint={money(p.deduction_self)}
                suffix="đ"
                step={100000}
                min={0}
                readOnly={readOnly}
                value={p.deduction_self}
                onChange={(v) => setP("deduction_self", v)}
              />
              <ParamField
                label="Giảm trừ mỗi người phụ thuộc"
                hint={money(p.deduction_dependent)}
                suffix="đ"
                step={100000}
                min={0}
                readOnly={readOnly}
                value={p.deduction_dependent}
                onChange={(v) => setP("deduction_dependent", v)}
              />
            </div>
          </section>

          <div className="cl-table__wrap">
            <table className="cl-table">
              <thead>
                <tr>
                  <th style={{ width: 80 }}>Bậc</th>
                  <th>Thu nhập tính thuế đến</th>
                  <th className="num" style={{ width: 160 }}>
                    Thuế suất
                  </th>
                  {!readOnly && <th style={{ width: 56 }} aria-label="Xóa" />}
                </tr>
              </thead>
              <tbody>
                {brackets.map((b, i) => (
                  <tr
                    key={b.key}
                    className={bracketErrors.has(i) ? "cl-row--invalid" : ""}
                  >
                    <td className="mono">
                      <strong>Bậc {i + 1}</strong>
                    </td>
                    <td>
                      <NumInput
                        value={b.up_to}
                        disabled={readOnly || busy}
                        suffix={b.up_to == null ? undefined : "đ"}
                        step={1000000}
                        min={0}
                        placeholder="∞ (bậc cao nhất)"
                        invalid={bracketErrors.has(i)}
                        onChange={(v) =>
                          setBrackets((bs) =>
                            bs.map((x, j) =>
                              j === i ? { ...x, up_to: v } : x,
                            ),
                          )
                        }
                      />
                      {b.up_to != null && (
                        <span className="cl-cell__sub">{money(b.up_to)}</span>
                      )}
                    </td>
                    <td className="num">
                      <NumInput
                        value={Math.round(b.rate * 100)}
                        disabled={readOnly || busy}
                        suffix="%"
                        step={1}
                        min={0}
                        max={100}
                        invalid={bracketErrors.has(i)}
                        onChange={(v) =>
                          setBrackets((bs) =>
                            bs.map((x, j) =>
                              j === i ? { ...x, rate: (v ?? 0) / 100 } : x,
                            ),
                          )
                        }
                      />
                    </td>
                    {!readOnly && (
                      <td className="act">
                        <button
                          type="button"
                          className="btn btn--ghost"
                          title="Xóa bậc này"
                          onClick={() =>
                            setBrackets((bs) => bs.filter((_, j) => j !== i))
                          }
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {bracketErrors.size > 0 && (
            <p className="cl-err">
              Mức của các bậc phải TĂNG DẦN · chỉ bậc CUỐI được để trống (∞) ·
              thuế suất từ 0 đến 100%.
            </p>
          )}
          {!readOnly && (
            <div className="cl-note">
              <Button variant="ghost" onClick={addBracket}>
                + Thêm bậc
              </Button>
            </div>
          )}
        </div>
      </div>

      <div className="cl-card">
        <h3 className="cl-card__title">khấu trừ đi trễ / về sớm</h3>
        <p className="cl-card__desc">
          Áp cho buổi đi trễ / về sớm KHÔNG phép (quá dung sai ca) — khấu trừ
          theo TỪNG LẦN
          {/* tra bảng theo số phút, Chủ nhật ×2 phút. Máy tự tính từ chấm
          công sẽ có ở bước sau; hiện dùng ở ô “Tính nhanh khấu trừ” của modal Sửa
          lương. */}
        </p>
        <div className="cl-card__body">
          <div className="cl-table__wrap">
            <table className="cl-table">
              <thead>
                <tr>
                  <th style={{ width: 80 }}>Bậc</th>
                  <th>Đến phút (∞ = trên hết)</th>
                  <th className="num" style={{ width: 200 }}>
                    Số tiền / lần
                  </th>
                  {!readOnly && <th style={{ width: 56 }} aria-label="Xóa" />}
                </tr>
              </thead>
              <tbody>
                {penalties.map((b, i) => (
                  <tr
                    key={b.key}
                    className={penaltyErrors.has(i) ? "cl-row--invalid" : ""}
                  >
                    <td className="mono">
                      <strong>Bậc {i + 1}</strong>
                    </td>
                    <td>
                      <NumInput
                        value={b.up_to_minute}
                        disabled={readOnly || busy}
                        suffix={b.up_to_minute == null ? undefined : "phút"}
                        step={5}
                        min={0}
                        placeholder="∞ (trên hết)"
                        invalid={penaltyErrors.has(i)}
                        onChange={(v) =>
                          setPenalties((bs) =>
                            bs.map((x, j) =>
                              j === i ? { ...x, up_to_minute: v } : x,
                            ),
                          )
                        }
                      />
                    </td>
                    <td className="num">
                      <NumInput
                        value={b.amount}
                        disabled={readOnly || busy}
                        suffix="đ"
                        step={10000}
                        min={0}
                        placeholder="0"
                        invalid={penaltyErrors.has(i)}
                        onChange={(v) =>
                          setPenalties((bs) =>
                            bs.map((x, j) =>
                              j === i ? { ...x, amount: v ?? 0 } : x,
                            ),
                          )
                        }
                      />
                      <span className="cl-cell__sub">{money(b.amount)}</span>
                    </td>
                    {!readOnly && (
                      <td className="act">
                        <button
                          type="button"
                          className="btn btn--ghost"
                          title="Xóa bậc này"
                          onClick={() =>
                            setPenalties((bs) => bs.filter((_, j) => j !== i))
                          }
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {penaltyErrors.size > 0 && (
            <p className="cl-err">
              Số phút của các bậc phải TĂNG DẦN · chỉ bậc CUỐI được để trống (∞)
              · số tiền ≥ 0.
            </p>
          )}
          {!readOnly && (
            <div className="cl-note">
              <Button variant="ghost" onClick={addPenalty}>
                + Thêm bậc
              </Button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

const INSURANCE_ROWS: {
  label: string;
  er: "bhxh_rate_er" | "bhyt_rate_er" | "bhtn_rate_er";
  ee: "bhxh_rate" | "bhyt_rate" | "bhtn_rate";
}[] = [
  { label: "BHXH", er: "bhxh_rate_er", ee: "bhxh_rate" },
  { label: "BHYT", er: "bhyt_rate_er", ee: "bhyt_rate" },
  { label: "BHTN", er: "bhtn_rate_er", ee: "bhtn_rate" },
];
