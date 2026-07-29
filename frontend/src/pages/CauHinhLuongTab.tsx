// Cấu hình lương — MỘT tab của màn Lương (không phải màn riêng), 3 tab con:
//   • Cơ chế lương theo bộ phận — 8 tham số toàn công ty + 4 thành phần lương của tổ.
//   • Danh mục khoản thu nhập  — mỗi khoản một dòng + ô tích "Chịu thuế" (chốt chủ 27/07/2026).
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
  type ComponentHolders,
  type EmployeeRow,
  type ComponentKind,
  type Department,
  type DeptComponent,
  type LatePenaltyBracket,
  type PayrollComponent,
  type PayrollParams,
  type PitBracket,
  type SalaryComponentKey,
} from "../api/client";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DiscardChangesDialog } from "../components/DiscardChangesDialog";
import { KhoanRatesEditor } from "../components/KhoanRatesEditor";
import { money } from "../utils/format";
import "./luong.css";
import "./rebuild-catalog.css";

// --- Hằng dùng chung --------------------------------------------------------

type SubTab = "cochE" | "danhmuc" | "phucap";

const SUB_TABS: { key: SubTab; label: string }[] = [
  { key: "cochE", label: "Cơ chế lương theo bộ phận" },
  { key: "danhmuc", label: "Danh mục khoản thu nhập" },
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
  // Tab "Danh mục khoản thu nhập" KHÔNG bao giờ dirty: mọi thao tác (thêm/sửa/xoá/bật cờ) là
  // lệnh dứt điểm, lưu ngay — không có nháp nào để mất khi đổi tab.
  const tabDirty: Record<SubTab, boolean> = {
    cochE: dirtyA || dirtyComps,
    danhmuc: false,
    phucap: dirtyIns || dirtyTax || dirtyPenalty,
  };
  const anyDirty = tabDirty.cochE || tabDirty.danhmuc || tabDirty.phucap;

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

      {sub === "danhmuc" && <DanhMucTab token={token} readOnly={readOnly} />}

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
  "phat_cap_pct",
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

  // "Bật sản xuất" tính theo CÂY: chính tổ tích, HOẶC có tổ tiên tích — đúng ghi chú ở
  // `client.ts:848` ("Effective tính theo cây ở FE"). Chỉ soi mỗi cờ của chính tổ thì tổ con
  // của khối Sản xuất sẽ không được coi là sản xuất.
  const laSanXuat = useMemo(() => {
    const byId = new Map(depts.map((d) => [d.id, d]));
    let cur = deptId == null ? undefined : byId.get(deptId);
    const daQua = new Set<number>();          // chặn vòng lặp nếu cây bị khai sai
    while (cur && !daQua.has(cur.id)) {
      if (cur.la_san_xuat) return true;
      daQua.add(cur.id);
      cur = cur.parent_id == null ? undefined : byId.get(cur.parent_id);
    }
    return false;
  }, [depts, deptId]);
  const toTruongUserId = depts.find((d) => d.id === deptId)?.head_user_id ?? null;

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

      {/* Chủ 29/07/2026: "tổ nào bật sản xuất VÀ lương khoán thì nó sẽ hiện cái form điền %". */}
      {khoanOn && laSanXuat && deptId != null && (
        <LeaderBonusEditor
          token={token}
          departmentId={deptId}
          deptName={deptName}
          hasLeader={toTruongUserId != null}
          readOnly={readOnly}
        />
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

// --- Thưởng/phạt TỔ TRƯỞNG theo tỷ lệ hàng lỗi (chủ 29/07/2026) -------------
// "Hàng lỗi khoảng 5% thì thưởng 2% trên tổng, lỗi trên 10% thì bị trừ 10% trên tổng.
//  % này là TIỀN đó nha." → % tính trên TỔNG TIỀN KHOÁN của tổ; dương = thưởng, âm = phạt.
//
// ⚠️ Engine CHƯA áp bảng này (tổng khoán hiện luôn = 0 vì chưa có nguồn sản lượng) — banner
// vàng dưới đây nói thẳng điều đó. ĐỪNG GỠ: khai xong mà tưởng đã chạy là mất niềm tin.

type BracketRow = { up_to: number | null; rate: number; note: string };

function LeaderBonusEditor({
  token,
  departmentId,
  deptName,
  hasLeader,
  readOnly,
}: {
  token: string;
  departmentId: number;
  deptName: string;
  hasLeader: boolean;
  readOnly: boolean;
}) {
  const [rows, setRows] = useState<BracketRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [thuLoi, setThuLoi] = useState(7);          // ô thử nhanh: tỷ lệ lỗi
  const [thuKhoan, setThuKhoan] = useState(0);      // tổng khoán giả định

  useEffect(() => {
    let alive = true;
    api.luong
      .leaderBrackets(token, departmentId)
      .then((r) => {
        if (!alive) return;
        setRows(
          r.items.map((b) => ({
            up_to: b.up_to_defect_pct,
            rate: b.rate_pct,
            note: b.note ?? "",
          })),
        );
        setErr(null);
      })
      .catch((e) => alive && setErr(errText(e)));
    return () => {
      alive = false;
    };
  }, [token, departmentId]);

  function patch(i: number, f: Partial<BracketRow>) {
    setRows((rs) => (rs ?? []).map((r, k) => (k === i ? { ...r, ...f } : r)));
  }

  function them() {
    setRows((rs) => {
      const cur = rs ?? [];
      // Gợi ý rule-based: mốc mới = mốc kế cuối + 5. Bậc "trở lên" luôn giữ ở cuối.
      const coMoc = cur.filter((r) => r.up_to != null);
      const moc = coMoc.length ? (coMoc[coMoc.length - 1].up_to as number) + 5 : 5;
      const cuoi = cur.filter((r) => r.up_to == null);
      return [...coMoc, { up_to: moc, rate: 0, note: "" }, ...(cuoi.length ? cuoi : [
        { up_to: null, rate: 0, note: "" },
      ])];
    });
  }

  async function luu() {
    setBusy(true);
    setErr(null);
    setOk(null);
    try {
      const r = await api.luong.setLeaderBrackets(token, departmentId, (rows ?? []).map((x) => ({
        up_to_defect_pct: x.up_to,
        rate_pct: x.rate,
        note: x.note.trim() || null,
      })));
      setRows(
        r.items.map((b) => ({
          up_to: b.up_to_defect_pct,
          rate: b.rate_pct,
          note: b.note ?? "",
        })),
      );
      setOk("Đã lưu bậc thưởng/phạt tổ trưởng.");
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }

  /** Tra bậc — MIRROR đúng `PieceWorkService.leader_bonus_pct` ở backend: bậc ĐẦU TIÊN có
   *  `lỗi ≤ trần` thắng. Hai bên lệch nhau thì ô thử nhanh nói dối. */
  function traBac(loi: number): BracketRow | null {
    for (const r of rows ?? []) {
      if (r.up_to == null || loi <= r.up_to) return r;
    }
    const rs = rows ?? [];
    return rs.length ? rs[rs.length - 1] : null;
  }

  const bacTrung = traBac(thuLoi);
  const tienThu = bacTrung ? Math.round((thuKhoan * bacTrung.rate) / 100) : 0;

  /** Đọc bảng mốc thành câu tiếng Việt — nhìn bảng số khó hình dung, đọc câu thì ra ngay. */
  const cauDoc = (rows ?? [])
    .map((r, i, arr) => {
      const truoc = i === 0 ? null : arr[i - 1].up_to;
      const pham =
        r.up_to == null
          ? `trên ${truoc ?? 0}%`
          : truoc == null
            ? `≤ ${r.up_to}%`
            : `trên ${truoc}–${r.up_to}%`;
      const act =
        r.rate > 0 ? `thưởng ${r.rate}%` : r.rate < 0 ? `phạt ${Math.abs(r.rate)}%` : "không thưởng/phạt";
      return `lỗi ${pham} ⇒ ${act}`;
    })
    .join(" · ");

  return (
    <div className="cl-card">
      <div className="cl-card__head">
        <div>
          <h3 className="cl-card__title">Thưởng / phạt tổ trưởng theo chất lượng — {deptName}</h3>
          <p className="cl-card__desc">
            Tỷ lệ hàng lỗi của tổ càng thấp thì tổ trưởng được thưởng càng nhiều; lỗi vượt mốc
            thì bị trừ. Số % ở đây là <b>% trên TỔNG TIỀN KHOÁN của tổ</b> — tức là tiền.
          </p>
        </div>
        {!readOnly && (
          <Button variant="ghost" onClick={them}>
            + Thêm bậc
          </Button>
        )}
      </div>

      <div className="cl-card__body">
        {/* Sự thật phải nói thẳng: khai xong CHƯA ra tiền. */}
        <div className="banner banner--warn">
          <span>
            Tiền khoán của tổ hiện <b>luôn = 0</b> vì chưa có nguồn nhập sản lượng — khai mốc ở
            đây là <b>chuẩn bị trước</b>, chưa ra tiền cho tới khi mở lại phần sản lượng.
          </span>
        </div>
        {!hasLeader && (
          <div className="banner banner--warn">
            <span>
              Tổ này <b>chưa có tổ trưởng</b> — khai mốc xong vẫn chưa có ai nhận. Gán ở màn
              <b> Phòng ban</b>.
            </span>
          </div>
        )}
        {err && <div className="banner banner--error">{err}</div>}
        {ok && <div className="banner banner--success">{ok}</div>}

        {rows === null ? (
          <p className="cl-hint-inline">Đang tải bậc thưởng/phạt…</p>
        ) : rows.length === 0 ? (
          <div className="cl-empty">
            <span className="cl-empty__title">Tổ này chưa áp thưởng/phạt tổ trưởng</span>
            <span className="cl-empty__desc">
              Bấm “+ Thêm bậc” để khai. Ví dụ: lỗi ≤ 5% ⇒ thưởng 2%; trên 10% ⇒ phạt 10%.
            </span>
          </div>
        ) : (
          <>
            <div className="cl-table__wrap">
              <table className="cl-table">
                <thead>
                  <tr>
                    <th style={{ width: 60 }}>Bậc</th>
                    <th style={{ width: 190 }}>Tỷ lệ lỗi tới (%)</th>
                    <th style={{ width: 210 }}>Thưởng (+) / Phạt (−) %</th>
                    <th>Ghi chú</th>
                    {!readOnly && <th style={{ width: 56 }} aria-label="Thao tác" />}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i}>
                      <td>{i + 1}</td>
                      <td>
                        {r.up_to == null ? (
                          <span className="cl-muted">trở lên (mọi tỷ lệ cao hơn)</span>
                        ) : (
                          <input
                            type="number"
                            min={0}
                            max={100}
                            step={1}
                            disabled={readOnly}
                            value={r.up_to}
                            onChange={(e) => patch(i, { up_to: Number(e.target.value) })}
                          />
                        )}
                      </td>
                      <td>
                        <div className="cl-lb__rate">
                          <input
                            type="number"
                            min={-100}
                            max={100}
                            step={1}
                            disabled={readOnly}
                            value={r.rate}
                            onChange={(e) => patch(i, { rate: Number(e.target.value) })}
                          />
                          {/* Dấu âm dễ đọc lướt thành dương ⇒ hiện chip chữ cho chắc. */}
                          <span
                            className={`ns-badge ${
                              r.rate > 0
                                ? "ns-badge--ok"
                                : r.rate < 0
                                  ? "ns-badge--warn"
                                  : "ns-badge--muted"
                            }`}
                          >
                            {r.rate > 0 ? "Thưởng" : r.rate < 0 ? "Phạt" : "Hòa"}
                          </span>
                        </div>
                      </td>
                      <td>
                        <input
                          type="text"
                          maxLength={255}
                          disabled={readOnly}
                          value={r.note}
                          onChange={(e) => patch(i, { note: e.target.value })}
                        />
                      </td>
                      {!readOnly && (
                        <td className="act">
                          <button
                            type="button"
                            className="btn btn--ghost"
                            aria-label={`Xoá bậc ${i + 1}`}
                            onClick={() => setRows((rs) => (rs ?? []).filter((_, k) => k !== i))}
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

            <p className="cl-hint-inline cl-lb__read">{cauDoc}</p>

            {/* Thử nhanh — bám đúng helper "Tính nhanh phạt" của bảng phạt đi trễ. */}
            <div className="cl-lb__try">
              <label className="ns-field">
                <span className="ns-field__label">Thử: tỷ lệ lỗi (%)</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={thuLoi}
                  onChange={(e) => setThuLoi(Number(e.target.value))}
                />
              </label>
              <label className="ns-field">
                <span className="ns-field__label">Tổng khoán giả định (đ)</span>
                <input
                  type="number"
                  min={0}
                  step={1000000}
                  value={thuKhoan}
                  onChange={(e) => setThuKhoan(Number(e.target.value))}
                />
              </label>
              <div className="cl-lb__out">
                {bacTrung ? (
                  <>
                    Trúng bậc <b>{(rows ?? []).indexOf(bacTrung) + 1}</b> ⇒{" "}
                    <b>{bacTrung.rate > 0 ? `+${bacTrung.rate}` : bacTrung.rate}%</b>
                    {thuKhoan > 0 && (
                      <>
                        {" "}
                        ⇒{" "}
                        <b className={tienThu < 0 ? "lg-minus" : ""}>
                          {tienThu < 0 ? "−" : "+"}
                          {money(Math.abs(tienThu))}đ
                        </b>
                      </>
                    )}
                  </>
                ) : (
                  "Chưa khai bậc nào."
                )}
              </div>
            </div>

            {!readOnly && (
              <div className="cl-lb__foot">
                <Button onClick={() => void luu()} disabled={busy}>
                  {busy ? "Đang lưu…" : "Lưu bậc thưởng/phạt"}
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// --- Tab con: Danh mục khoản thu nhập — TẦNG 1 (PRD v2, chốt chủ 27/07/2026) --
// Đây là BƯỚC 1 của quy trình 2 bước: muốn có khoản mới thì tạo Ở ĐÂY trước, rồi mới sang
// hồ sơ nhân viên (Lương → Lương nhân viên → Sửa lương) CHỌN khoản đó và nhập tiền. Hồ sơ NV
// không có ô gõ tên khoản tự do — nếu không, mỗi người một cách gọi và cờ "Chịu thuế" loạn.
// Cờ `is_taxable` CHỈ sống ở tầng này; tầng 2/3 chép lại, không sửa được.
// LƯU NGAY từng thao tác (không gom vào thanh lưu sticky): xoá là lệnh dứt điểm và câu báo
// phải khớp ĐÚNG việc backend vừa làm — xoá hẳn hay chỉ ngừng áp dụng.

type CompDraft = { name: string; kind: ComponentKind; is_taxable: boolean };
const NEW_COMPONENT: CompDraft = { name: "", kind: "thu", is_taxable: true };

function DanhMucTab({ token, readOnly }: { token: string; readOnly: boolean }) {
  // null = ĐANG TẢI. Khởi tạo [] sẽ hiện "chưa có khoản nào" ngay lúc còn đang fetch — báo SAI.
  const [items, setItems] = useState<PayrollComponent[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  // Form thêm/sửa dùng chung — `id: null` = thêm mới.
  const [form, setForm] = useState<{ id: number | null; draft: CompDraft } | null>(null);
  const [formBusy, setFormBusy] = useState(false);
  const [formErr, setFormErr] = useState<string | null>(null);
  const [del, setDel] = useState<PayrollComponent | null>(null);
  const [delBusy, setDelBusy] = useState(false);
  const [delErr, setDelErr] = useState<string | null>(null);
  // Danh sách NV còn giữ một khoản ĐÃ NGỪNG ÁP DỤNG. `null` = chưa mở modal; `items` rỗng =
  // mở rồi mà không còn ai. Lương vẫn trả đủ — modal này để HCNS biết còn ai phải gỡ.
  const [holders, setHolders] = useState<ComponentHolders | null>(null);
  const [holdersBusy, setHoldersBusy] = useState(false);
  const [holdersErr, setHoldersErr] = useState<string | null>(null);
  // Gán hàng loạt (chủ 28/07/2026). `bulk` = khoản đang gán; null = modal đóng.
  const [bulk, setBulk] = useState<PayrollComponent | null>(null);

  const load = useCallback(() => {
    api.luong.components
      .list(token)
      .then((r) => {
        setItems(r.items);
        setErr(null);
      })
      // GIỮ NGUYÊN `items`: gán [] khi lỗi sẽ hiện "chưa có khoản nào" — báo SAI (tải hỏng
      // chứ danh mục không rỗng). Lần đầu hỏng thì `items` vẫn null ⇒ render khối "thử lại".
      .catch((e) => setErr(errText(e)));
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

  /** Ai còn giữ khoản đã ngừng áp dụng. Gọi lúc BẤM (không tải sẵn cho cả bảng): danh sách
   *  này chỉ cần khi người dùng thật sự muốn xem, tải sẵn là N request thừa mỗi lần vào tab. */
  async function openHolders(c: PayrollComponent) {
    setHoldersBusy(true);
    setHoldersErr(null);
    setHolders({ component_id: c.id, component_name: c.name, items: [] });
    try {
      setHolders(await api.luong.components.holders(token, c.id));
    } catch (e) {
      setHoldersErr(errText(e));
    } finally {
      setHoldersBusy(false);
    }
  }

  function openBulk(c: PayrollComponent) {
    setErr(null);
    setBulk(c);
  }

  /** Báo việc VỪA làm. `sticky` cho câu quan trọng (ngừng áp dụng) — không tự tắt sau vài giây. */
  function say(msg: string, sticky = false) {
    setOk(msg);
    if (!sticky)
      window.setTimeout(() => setOk((cur) => (cur === msg ? null : cur)), 5000);
  }

  async function patch(c: PayrollComponent, body: Parameters<typeof api.luong.components.update>[2], msg: string) {
    setBusyId(c.id);
    setErr(null);
    try {
      const updated = await api.luong.components.update(token, c.id, body);
      setItems((list) => (list ?? []).map((x) => (x.id === c.id ? updated : x)));
      say(msg);
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusyId(null);
    }
  }

  async function saveForm() {
    if (!form) return;
    const name = form.draft.name.trim();
    if (!name) {
      setFormErr("Nhập tên khoản.");
      return;
    }
    setFormBusy(true);
    setFormErr(null);
    try {
      if (form.id == null) {
        // Khoản mới xuống CUỐI danh mục (không chen giữa các khoản kế toán đang quen thứ tự).
        const maxSort = (items ?? []).reduce((m, c) => Math.max(m, c.sort_order), 0);
        await api.luong.components.create(token, {
          name,
          kind: form.draft.kind,
          is_taxable: form.draft.is_taxable,
          sort_order: maxSort + 10,
        });
        say(`Đã thêm khoản “${name}”.`);
      } else {
        await api.luong.components.update(token, form.id, {
          name,
          kind: form.draft.kind,
          is_taxable: form.draft.is_taxable,
        });
        say(`Đã lưu khoản “${name}”.`);
      }
      setForm(null);
      load();
    } catch (e) {
      setFormErr(errText(e));
    } finally {
      setFormBusy(false);
    }
  }

  /** ĐỌC kết quả trả về rồi mới báo: backend có thể chỉ NGỪNG ÁP DỤNG chứ không xoá.
   *  Câu báo lấy NGUYÊN VĂN `message` của backend — tự chế lại là nói sai việc vừa làm
   *  (và làm lệch với thông điệp chủ đã duyệt). */
  async function confirmDelete() {
    if (!del) return;
    const name = del.name;
    setDelBusy(true);
    setDelErr(null);
    try {
      const res = await api.luong.components.remove(token, del.id);
      setDel(null);
      load();
      if (res.deleted) say(res.message || `Đã xoá khoản “${name}”.`);
      else if (res.deactivated)
        say(
          res.message ||
            `Khoản “${name}” đã có phát sinh dữ liệu nên chỉ chuyển sang NGỪNG SỬ DỤNG.`,
          true,
        );
      else
        say(
          res.message ||
            "Hệ thống không xoá và cũng không ngừng áp dụng khoản này. Tải lại danh mục để xem trạng thái thật.",
          true,
        );
    } catch (e) {
      setDelErr(errText(e));
    } finally {
      setDelBusy(false);
    }
  }

  /** Đã có số liệu (gán cho NV hoặc đã chạy qua kỳ lương) ⇒ backend KHÔNG xoá cứng. */
  const delUsed = del ? del.employee_count > 0 || del.period_count > 0 : false;

  const editing = form?.id != null;

  return (
    <>
      <div className="cl-card">
        <div className="cl-card__head">
          <div>
            <h3 className="cl-card__title">Danh mục khoản thu nhập</h3>
            <p className="cl-card__desc">
              <b>Bước 1</b> của quy trình 2 bước: khoản mới phải tạo ở đây
              trước. <b>Bước 2</b> — sang <b>Lương → Lương nhân viên → Sửa
              lương</b> chọn khoản này cho từng người và nhập số tiền. Ô tích
              “Chịu thuế” quyết định khoản có tính vào thu nhập chịu thuế TNCN
              hay không, và <b>chỉ khai ở đây</b>.
            </p>
          </div>
          {!readOnly && (
            <Button
              variant="ghost"
              onClick={() => {
                setFormErr(null);
                setForm({ id: null, draft: NEW_COMPONENT });
              }}
            >
              + Thêm khoản
            </Button>
          )}
        </div>

        <div className="cl-card__body">
          {err && <div className="banner banner--error">{err}</div>}
          {ok && <div className="banner banner--success">{ok}</div>}

          {items === null ? (
            err ? (
              <div className="cl-empty">
                <span className="cl-empty__title">
                  Không tải được danh mục khoản thu nhập
                </span>
                <span className="cl-empty__desc">
                  Danh mục có thể vẫn còn nguyên — chỉ là lần tải này hỏng.
                </span>
                <div className="cl-note">
                  <Button variant="ghost" onClick={load}>
                    Thử lại
                  </Button>
                </div>
              </div>
            ) : (
              <p className="cl-hint-inline">Đang tải danh mục…</p>
            )
          ) : items.length === 0 ? (
            <div className="cl-empty">
              <span className="cl-empty__title">
                Chưa có khoản nào trong danh mục
              </span>
              <span className="cl-empty__desc">
                Bấm “+ Thêm khoản” để khai khoản đầu tiên (vd Trang phục · Tiền
                ăn ca · Hỗ trợ đi lại). Chưa có khoản ở đây thì hồ sơ nhân viên
                cũng chưa chọn được gì.
              </span>
            </div>
          ) : (
            <div className="cl-table__wrap">
              <table className="cl-table">
                <thead>
                  <tr>
                    <th>Tên khoản</th>
                    <th style={{ width: 96 }}>Loại</th>
                    <th style={{ width: 132 }}>Chịu thuế</th>
                    <th className="num" style={{ width: 176 }}>
                      Đang dùng
                    </th>
                    {!readOnly && (
                      <th style={{ width: 150 }} aria-label="Thao tác" />
                    )}
                  </tr>
                </thead>
                <tbody>
                  {items.map((c) => (
                    <tr key={c.id} className={c.is_active ? "" : "cl-dm--off"}>
                      <td>
                        <strong>{c.name}</strong>
                        {!c.is_active && (
                          <span className="rc-pill rc-pill--off cl-dm__tag">
                            Ngừng áp dụng
                          </span>
                        )}
                        {c.note && (
                          <span className="cl-cell__sub">{c.note}</span>
                        )}
                        {/* Ngừng áp dụng mà NV còn giữ ⇒ lương VẪN TRẢ khoản này. Không nói
                            ra thì tắt khoản xong không ai biết còn ai đang dính. */}
                        {!c.is_active && c.employee_count > 0 && (
                          <button
                            type="button"
                            className="cl-dm__holders"
                            onClick={() => openHolders(c)}
                          >
                            Xem {c.employee_count} người đang gán
                          </button>
                        )}
                      </td>
                      <td>
                        <span
                          className={`ns-badge ${c.kind === "tru" ? "ns-badge--danger" : "ns-badge--ok"}`}
                        >
                          {c.kind === "tru" ? "Trừ" : "Thu"}
                        </span>
                      </td>
                      <td>
                        <label className="cl-check">
                          <input
                            type="checkbox"
                            checked={c.is_taxable}
                            disabled={readOnly || busyId === c.id}
                            aria-label={`Chịu thuế — ${c.name}`}
                            onChange={(e) =>
                              patch(
                                c,
                                { is_taxable: e.target.checked },
                                e.target.checked
                                  ? `“${c.name}” giờ TÍNH vào thu nhập chịu thuế TNCN.`
                                  : `“${c.name}” giờ được MIỄN thuế TNCN.`,
                              )
                            }
                          />
                          <span>{c.is_taxable ? "Chịu thuế" : "Miễn thuế"}</span>
                        </label>
                      </td>
                      {/* "N nhân viên · M kỳ lương" — HR hình dung được mức độ ảnh hưởng;
                          "N dòng lương" của bản cũ nói 100 dòng cùng một tháng thành 100. */}
                      <td className="num">
                        {c.employee_count > 0 || c.period_count > 0 ? (
                          <>
                            {c.employee_count} nhân viên · {c.period_count} kỳ
                            lương
                            <span className="cl-cell__sub">
                              không xoá cứng được
                            </span>
                          </>
                        ) : (
                          <span className="cl-muted">chưa dùng</span>
                        )}
                      </td>
                      {!readOnly && (
                        <td className="act">
                          <button
                            type="button"
                            className="btn btn--ghost"
                            disabled={busyId === c.id}
                            onClick={() => {
                              setFormErr(null);
                              setForm({
                                id: c.id,
                                draft: {
                                  name: c.name,
                                  kind: c.kind,
                                  is_taxable: c.is_taxable,
                                },
                              });
                            }}
                          >
                            Sửa
                          </button>
                          {/* Gán hàng loạt (chủ 28/07/2026): tạo khoản xong mà phải mở hồ sơ
                              từng người thì nhà máy 40–100 người không dùng được. Khoản đã
                              ngừng áp dụng thì không gán mới (luật sẵn có ở backend). */}
                          {c.is_active && (
                            <button
                              type="button"
                              className="btn btn--ghost"
                              disabled={busyId === c.id}
                              onClick={() => openBulk(c)}
                            >
                              Gán cho nhân viên
                            </button>
                          )}
                          {c.is_active ? (
                            <button
                              type="button"
                              className="btn btn--ghost"
                              title="Xoá khoản này"
                              aria-label={`Xoá khoản ${c.name}`}
                              disabled={busyId === c.id}
                              onClick={() => {
                                setDelErr(null);
                                setDel(c);
                              }}
                            >
                              <Trash2 size={14} />
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="btn btn--ghost"
                              disabled={busyId === c.id}
                              onClick={() =>
                                patch(
                                  c,
                                  { is_active: true },
                                  `Đã bật lại khoản “${c.name}”.`,
                                )
                              }
                            >
                              Bật lại
                            </button>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="cl-hint-inline">
            Bỏ tích “Chịu thuế” = khoản đó không tính vào thu nhập chịu thuế
            TNCN. Đổi cờ chỉ ảnh hưởng kỳ tính từ đó về sau; kỳ đã chốt giữ
            nguyên số cũ.
          </p>
          <p className="cl-hint-inline">
            Khoản đã có số liệu thì KHÔNG xoá cứng được — hệ thống chỉ chuyển
            sang <b>Ngừng áp dụng</b> để phiếu lương các kỳ cũ vẫn còn đủ dòng.
            Người đang được gán khoản đó <b>vẫn được trả tiền như cũ</b>: bấm
            “Xem N người đang gán” để gỡ từng người ở{" "}
            <b>Lương → Lương nhân viên</b>.
          </p>
          <p className="cl-hint-inline">
            Thưởng nóng / khoản chỉ có <b>một tháng</b> thì đừng tạo danh mục
            mới: dùng sẵn <b>“Thu nhập khác (chịu thuế)”</b> hoặc{" "}
            <b>“(miễn thuế)”</b>, khai thẳng ở <b>Bảng lương → Sửa dòng → Khoản
            phát sinh tháng này</b> kèm ghi chú.
          </p>
        </div>
      </div>

      <ConfirmDialog
        open={form !== null}
        title={editing ? "Sửa khoản thu nhập" : "Thêm khoản thu nhập"}
        confirmLabel={editing ? "Lưu khoản" : "Thêm khoản"}
        busy={formBusy}
        error={formErr}
        onCancel={() => {
          if (!formBusy) setForm(null);
        }}
        onConfirm={saveForm}
      >
        {form && (
          <div className="rc-grid">
            <label className="rc-field rc-field--full">
              <span className="rc-field__label">Tên khoản</span>
              <div className="rc-input-wrapper">
                <input
                  className="rc-input"
                  autoFocus
                  maxLength={120}
                  placeholder="vd Trang phục · Tiền ăn ca · Hỗ trợ đi lại"
                  value={form.draft.name}
                  onChange={(e) =>
                    setForm((f) =>
                      f ? { ...f, draft: { ...f.draft, name: e.target.value } } : f,
                    )
                  }
                />
              </div>
              <span className="rc-field__hint">
                Tên này hiện nguyên văn trên phiếu lương của nhân viên.
              </span>
            </label>
            <label className="rc-field">
              <span className="rc-field__label">Loại khoản</span>
              <div className="rc-input-wrapper">
                <select
                  className="rc-input"
                  value={form.draft.kind}
                  onChange={(e) =>
                    setForm((f) =>
                      f
                        ? {
                            ...f,
                            draft: {
                              ...f.draft,
                              kind: e.target.value as ComponentKind,
                            },
                          }
                        : f,
                    )
                  }
                >
                  <option value="thu">Thu — cộng vào tổng lương</option>
                  <option value="tru">Trừ — khấu trừ vào thực nhận</option>
                </select>
              </div>
            </label>
            <label className="rc-field rc-field--check">
              <span className="rc-field__label">Chịu thuế TNCN</span>
              <input
                type="checkbox"
                className="cl-check__box"
                checked={form.draft.is_taxable}
                onChange={(e) =>
                  setForm((f) =>
                    f
                      ? {
                          ...f,
                          draft: { ...f.draft, is_taxable: e.target.checked },
                        }
                      : f,
                  )
                }
              />
            </label>
            <p className="rc-field__hint rc-field--full">
              Bỏ tích nếu khoản này được MIỄN thuế (trang phục · tiền ăn ca ·
              trợ cấp tiền nhà · hỗ trợ đi lại…). Tích = cộng vào thu nhập chịu
              thuế TNCN.
            </p>
          </div>
        )}
      </ConfirmDialog>

      <ConfirmDialog
        open={del !== null}
        danger
        title={`Xoá khoản “${del?.name ?? ""}”?`}
        confirmLabel={delUsed ? "Ngừng áp dụng khoản này" : "Xoá khoản"}
        busy={delBusy}
        error={delErr}
        onCancel={() => {
          if (!delBusy) setDel(null);
        }}
        onConfirm={confirmDelete}
      >
        {del &&
          (delUsed ? (
            <p className="cdlg__msg">
              Khoản này đã có phát sinh dữ liệu (gán cho{" "}
              <b>{del.employee_count} nhân viên</b>, đã chốt{" "}
              <b>{del.period_count} kỳ lương</b>) nên KHÔNG xoá vĩnh viễn được.
              Hệ thống sẽ chuyển sang <b>Ngừng áp dụng</b>: khoản biến mất khỏi
              danh sách chọn khi gán mới, còn phiếu lương các kỳ cũ giữ nguyên
              số đã trả.
              {del.employee_count > 0 && (
                <>
                  {" "}
                  Người đang được gán <b>vẫn tiếp tục được trả</b> khoản này cho
                  tới khi bạn gỡ ở <b>Lương → Lương nhân viên</b>.
                </>
              )}
            </p>
          ) : (
            <p className="cdlg__msg">
              Khoản này chưa gán cho ai và chưa qua kỳ lương nào nên sẽ được xoá
              hẳn khỏi danh mục.
            </p>
          ))}
      </ConfirmDialog>

      {/* Ai còn giữ khoản đã ngừng áp dụng — chỉ để XEM rồi đi gỡ, không thao tác tại chỗ:
          gỡ khoản là sửa TIỀN LƯƠNG của người ta, phải làm ở đúng màn hồ sơ lương. */}
      <ConfirmDialog
        open={holders !== null}
        hideConfirm
        wide
        title={`Đang gán khoản “${holders?.component_name ?? ""}”`}
        cancelLabel="Đóng"
        error={holdersErr}
        onConfirm={() => setHolders(null)}
        onCancel={() => setHolders(null)}
      >
        {holdersBusy ? (
          <p className="cdlg__msg">Đang tải danh sách…</p>
        ) : holders && holders.items.length === 0 ? (
          <p className="cdlg__msg">
            Không còn ai được gán khoản này.
          </p>
        ) : (
          <>
            <p className="cdlg__msg">
              <b>{holders?.items.length ?? 0} người</b> vẫn đang được trả khoản
              này mỗi tháng dù khoản đã ngừng áp dụng. Gỡ từng người ở{" "}
              <b>Lương → Lương nhân viên → Sửa lương</b>.
            </p>
            <ul className="cl-holders">
              {holders?.items.map((h) => (
                <li key={h.employee_id}>
                  <span className="cl-holders__code">{h.code}</span>
                  {h.full_name}
                </li>
              ))}
            </ul>
          </>
        )}
      </ConfirmDialog>

      {bulk && (
        <BulkAssignDialog
          token={token}
          component={bulk}
          onClose={() => setBulk(null)}
          onDone={(msg) => {
            setBulk(null);
            load();          // đếm "N nhân viên" trên bảng phải nhảy theo
            say(msg, true);
          }}
        />
      )}
    </>
  );
}

// --- Gán hàng loạt một khoản cho nhiều NV (chủ 28/07/2026) ------------------
// Trước đây tạo khoản xong phải mở hồ sơ TỪNG người để thêm — nhà máy 40–100 người thì không
// dùng được. Chỗ nguy hiểm duy nhất ở màn này là ô "Ghi đè": bật lên là xoá mức riêng đã khai
// cho từng người và KHÔNG hoàn tác được, nên nó mặc định TẮT và khi bật phải cho xem trước
// đúng ai bị đổi từ bao nhiêu sang bao nhiêu.

/** Lấy HẾT nhân viên, phân trang cho tới khi đủ `total`.
 *
 * `GET /api/employees` chặn `size ≤ 200` (Query `le=200`) — gửi 500 là **422**, và vì gọi trong
 * `Promise.all` nên hỏng một cái là danh sách treo mãi ở "Đang tải…". Kẹp về 200 thì hết lỗi
 * nhưng ÂM THẦM SÓT người khi nhà máy vượt 200 — gán hàng loạt mà thiếu người thì tệ hơn là báo
 * lỗi. Nên lặp cho đủ. */
const EMP_PAGE = 200;
async function fetchAllEmployees(token: string): Promise<EmployeeRow[]> {
  const first = await api.employees.list(token, { page: 1, size: EMP_PAGE });
  const out = [...first.items];
  const pages = Math.ceil(first.total / EMP_PAGE);
  for (let p = 2; p <= pages; p++) {
    const r = await api.employees.list(token, { page: p, size: EMP_PAGE });
    out.push(...r.items);
  }
  return out;
}

function BulkAssignDialog({
  token,
  component,
  onClose,
  onDone,
}: {
  token: string;
  component: PayrollComponent;
  onClose: () => void;
  onDone: (msg: string) => void;
}) {
  const [emps, setEmps] = useState<EmployeeRow[] | null>(null);
  const [held, setHeld] = useState<Map<number, number> | null>(null);
  const [mode, setMode] = useState<"all" | "pick">("all");
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [q, setQ] = useState("");
  const [dept, setDept] = useState("");   // "" = mọi phòng ban/tổ; khác rỗng = department_id
  const [depts, setDepts] = useState<Department[]>([]);
  const [amount, setAmount] = useState(0);
  const [note, setNote] = useState("");
  const [overwrite, setOverwrite] = useState(false);   // ⚠️ mặc định TẮT — xem ghi chú khối trên
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([
      fetchAllEmployees(token),
      api.luong.components.employeeAmounts(token, component.id),
      // Lấy TỪ DANH MỤC phòng ban, KHÔNG suy từ nhân viên đã tải: suy từ nhân viên thì phòng
      // nào chưa có ai sẽ biến mất khỏi bộ lọc — người dùng biết phòng đó tồn tại mà không
      // thấy đâu, tưởng hệ thống mất dữ liệu.
      api.rbac.departments(token),
    ])
      .then(([all, amounts, dsPhong]) => {
        if (!alive) return;
        // Chỉ NV ĐANG LÀM VIỆC — rải phụ cấp cho người đã nghỉ là đẻ tiền cho hồ sơ chết.
        setEmps(all.filter((e) => e.status === "active" || e.status === "probation"));
        setHeld(new Map(amounts.items.map((x) => [x.employee_id, x.amount])));
        setDepts(dsPhong);
        setErr(null);
      })
      .catch((e) => alive && setErr(errText(e)));
    return () => {
      alive = false;
    };
  }, [token, component.id]);

  // Xổ theo CÂY: phòng cha rồi tới tổ con, tổ con thụt vào. Danh sách phẳng theo bảng chữ cái
  // làm mất quan hệ "tổ này thuộc phòng nào" — nhà máy có nhiều tổ cùng tên kiểu "Tổ 1".
  const deptOptions: { id: number; label: string }[] = [];
  const soNguoi = new Map<number, number>();
  for (const e of emps ?? []) {
    if (e.department_id != null) soNguoi.set(e.department_id, (soNguoi.get(e.department_id) ?? 0) + 1);
  }
  const duyet = (parentId: number | null, sau: number) => {
    for (const d of depts.filter((x) => (x.parent_id ?? null) === parentId)) {
      const n = soNguoi.get(d.id) ?? 0;
      deptOptions.push({
        id: d.id,
        // Số người hiện ngay trên nhãn: phòng "(0)" thì biết trước là lọc vào sẽ trống, khỏi
        // bấm rồi mới ngơ ngác.
        label: `${"  ".repeat(sau)}${sau ? "└ " : ""}${d.name} (${n})`,
      });
      duyet(d.id, sau + 1);
    }
  };
  duyet(null, 0);

  const shown = (emps ?? []).filter((e) => {
    const s = q.trim().toLowerCase();
    const hopTen =
      !s || e.full_name.toLowerCase().includes(s) || (e.code ?? "").toLowerCase().includes(s);
    return hopTen && (!dept || e.department_id === Number(dept));
  });
  // Người đã có mức riêng mà chưa xin ghi đè thì KHOÁ ⇒ "Chọn tất cả" cũng phải bỏ qua họ,
  // nếu không nút này lại đẩy vào những id mà backend sẽ bỏ qua — số trên màn nói dối.
  const chonDuoc = shown.filter((e) => overwrite || !held?.has(e.id));
  const targets = mode === "all" ? (emps ?? []) : (emps ?? []).filter((e) => picked.has(e.id));
  const willOverwrite = targets.filter((e) => held?.has(e.id)).length;
  const willAdd = targets.length - willOverwrite;

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      const res = await api.luong.components.bulkAssign(token, component.id, {
        amount,
        note: note.trim() || null,
        all_active: mode === "all",
        employee_ids: mode === "all" ? [] : [...picked],
        overwrite,
      });
      // Câu báo nói ĐÚNG việc vừa xảy ra: thêm mới và ghi đè là hai chuyện khác nhau.
      const parts = [`Đã thêm mới ${res.assigned} người`];
      if (res.overwritten) parts.push(`ghi đè ${res.overwritten} người`);
      if (res.skipped_existing) parts.push(`bỏ qua ${res.skipped_existing} người đã có mức riêng`);
      onDone(`“${component.name}”: ${parts.join(" · ")}.`);
    } catch (e) {
      setErr(errText(e));
      setBusy(false);
    }
  }

  return (
    <ConfirmDialog
      open
      wide
      title={`Gán “${component.name}” cho nhân viên`}
      confirmLabel={busy ? "Đang lưu…" : "Lưu"}
      cancelLabel="Hủy"
      error={err}
      confirmDisabled={busy || targets.length === 0 || amount < 0}
      onConfirm={() => void save()}
      onCancel={onClose}
    >
      <div className="cl-bulk">
        <div className="cl-bulk__modes">
          <label className="cl-check">
            <input type="radio" checked={mode === "all"} onChange={() => setMode("all")} />
            <span>Tất cả nhân viên đang làm việc{emps ? ` (${emps.length})` : ""}</span>
          </label>
          <label className="cl-check">
            <input type="radio" checked={mode === "pick"} onChange={() => setMode("pick")} />
            <span>Chọn cụ thể{mode === "pick" ? ` (${picked.size})` : ""}</span>
          </label>
        </div>

        {mode === "pick" && (
          <>
            {/* Lọc + chọn cả nhóm: "lọc tổ Bế → Chọn tất cả" là 2 cú bấm cho cả tổ, thay vì
                tick từng người. Cố ý KHÔNG phân trang — danh sách tick chọn mà chia trang thì
                tick xong sang trang khác là không còn nhìn thấy mình đã chọn ai. */}
            <div className="cl-bulk__tools">
              <input
                className="cc-input-text"
                placeholder="Tìm theo tên hoặc mã nhân viên…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
              <select
                value={dept}
                onChange={(e) => setDept(e.target.value)}
                aria-label="Lọc theo phòng ban / tổ"
              >
                <option value="">Tất cả phòng ban / tổ</option>
                {deptOptions.map((d) => (
                  <option key={d.id} value={String(d.id)}>
                    {d.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="cl-bulk__bar">
              <span>
                Đang hiện <b>{shown.length}</b> · đã chọn <b>{picked.size}</b>
              </span>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={chonDuoc.length === 0}
                onClick={() => setPicked((s) => new Set([...s, ...chonDuoc.map((e) => e.id)]))}
              >
                Chọn tất cả đang hiện ({chonDuoc.length})
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={picked.size === 0}
                onClick={() => setPicked(new Set())}
              >
                Bỏ chọn hết
              </button>
            </div>
            <div className="cl-bulk__list">
              {emps === null ? (
                <p className="cl-hint-inline">Đang tải danh sách nhân viên…</p>
              ) : shown.length === 0 ? (
                <p className="cl-hint-inline">Không tìm thấy ai khớp.</p>
              ) : (
                shown.map((e) => {
                  const cu = held?.get(e.id);
                  // Đã có mức riêng: KHOÁ khi chưa xin ghi đè — nhìn là biết ngay sẽ bị bỏ qua.
                  const locked = cu != null && !overwrite;
                  return (
                    <label
                      key={e.id}
                      className={`cl-bulk__row${locked ? " cl-bulk__row--locked" : ""}`}
                    >
                      <input
                        type="checkbox"
                        checked={picked.has(e.id)}
                        disabled={locked}
                        onChange={(ev) =>
                          setPicked((s) => {
                            const n = new Set(s);
                            if (ev.target.checked) n.add(e.id);
                            else n.delete(e.id);
                            return n;
                          })
                        }
                      />
                      <span className="cl-bulk__name">
                        <b>{e.code}</b> {e.full_name}
                      </span>
                      {cu != null && (
                        <span className={overwrite ? "cl-bulk__over" : "cl-bulk__has"}>
                          {overwrite
                            ? `${money(cu)}đ → ${money(amount)}đ`
                            : `đã có ${money(cu)}đ — bỏ qua`}
                        </span>
                      )}
                    </label>
                  );
                })
              )}
            </div>
          </>
        )}

        <div className="ns-grid">
          <label className="ns-field">
            <span className="ns-field__label">Mức tiền chung *</span>
            <input
              type="number"
              min={0}
              step={50000}
              value={amount}
              onChange={(e) => setAmount(Number(e.target.value))}
            />
          </label>
          <label className="ns-field">
            <span className="ns-field__label">Ghi chú (dùng chung cả lô)</span>
            <input
              type="text"
              maxLength={255}
              placeholder="vd: Áp dụng từ tháng 8"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
        </div>

        <label className="cl-check cl-bulk__ow">
          <input
            type="checkbox"
            checked={overwrite}
            onChange={(e) => setOverwrite(e.target.checked)}
          />
          <span>
            Ghi đè mức riêng đã có
            <span className="cl-cell__sub">
              Tắt: giữ nguyên mức riêng của người đã có. Bật: đổi hết về mức chung ở trên.
            </span>
          </span>
        </label>

        {overwrite && willOverwrite > 0 && (
          <div className="banner banner--warn">
            ⚠ Sẽ ghi đè mức riêng của <b>{willOverwrite} người</b>. Thao tác này{" "}
            <b>không hoàn tác được</b>.
          </div>
        )}
        <p className="cl-hint-inline">
          Sẽ thêm mới cho <b>{willAdd}</b> người
          {willOverwrite > 0 && !overwrite && <> · bỏ qua <b>{willOverwrite}</b> người đã có mức riêng</>}
          {willOverwrite > 0 && overwrite && <> · ghi đè <b>{willOverwrite}</b> người</>}.
        </p>
      </div>
    </ConfirmDialog>
  );
}

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
              {/* Trước 29/07/2026 số 30% viết cứng trong engine, không đổi được từ màn. */}
              <ParamField
                label="Trần khấu trừ kỷ luật"
                hint="Điều 102 BLLĐ: tiền phạt / bồi thường trừ vào lương KHÔNG QUÁ 30% lương thực trả sau BHXH và thuế. Đặt 0 = TẮT trần (trừ trọn số đã ghi)."
                suffix="%"
                step={1}
                min={0}
                max={100}
                readOnly={readOnly}
                value={toPct(p.phat_cap_pct)}
                onChange={(v) => setP("phat_cap_pct", v / 100)}
              />
              {/* Cảnh báo, KHÔNG chặn: chủ toàn quyền, nhưng phải thấy mình đang vượt mức luật. */}
              {(toPct(p.phat_cap_pct) > 30 || toPct(p.phat_cap_pct) === 0) && (
                <p className="cl-hint-inline cl-warn-legal">
                  ⚠{" "}
                  {toPct(p.phat_cap_pct) === 0
                    ? "Đang TẮT trần — phạt bao nhiêu trừ bấy nhiêu (thực nhận vẫn không âm)."
                    : `Đang đặt ${toPct(p.phat_cap_pct)}%, VƯỢT mức 30% của Điều 102 BLLĐ.`}{" "}
                  Đây là mức luật định, không phải chính sách công ty.
                </p>
              )}
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
