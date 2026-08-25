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
// (tách từ pages/CauHinhLuongTab.tsx).
// `Trash2` (lucide) đã bỏ: mọi nút xoá trên dòng nay đi qua `RowActionButton` — nút dùng icon
// `trash` của bộ `components/Icons.tsx` kèm tooltip + tín hiệu nguy hiểm.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type Department,
  type DeptComponent,
  type PayrollParams,
} from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { DiscardChangesDialog } from "../../../../components/DiscardChangesDialog";
import { CoCheTab } from "./tabs/CoCheTab";
import { DanhMucTab } from "./tabs/DanhMucTab";
import { PhuCapTab } from "./tabs/PhuCapTab";
import {
  PARAMS_A,
  PARAMS_INS,
  PARAMS_TAX,
  READONLY_NOTE,
  SAVED_NOTE,
  SUB_TABS,
} from "./shared/constants";
import {
  as2Draft,
  as2PenaltyDraft,
  errText,
  orderByTree,
  pick,
  restore,
  validateBrackets,
  validatePenalties,
} from "./shared/helpers";
import type {
  BracketDraft,
  PendingNav,
  PenaltyDraft,
  SubTab,
} from "./shared/types";
import "../../../luong.css";
import "../../../rebuild-catalog.css";

export function CauHinhLuongTab({
  token,
  readOnly,
  onDirtyChange,
  navigate,
}: {
  token: string;
  readOnly: boolean;
  onDirtyChange?: (dirty: boolean) => void;
  /** Chỉ dùng cho một đường: panel "Đơn giá khoán của tổ" → màn danh mục Công việc khoán. Bỏ trống
   *  thì panel vẫn khai được, chỉ mất đường dẫn (xem `KhoanRatesEditor.onMoDanhMuc`). */
  navigate?: (id: string) => void;
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
          navigate={navigate}
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
            {/* Việc CHÍNH của cả tab này là GHI cấu hình ⇒ nút cam (`accent`). `primary` trong
                bộ CSS này ra màu NAVY, không phải cam — đừng đổi ngược lại vì đọc tên lớp.
                Đây là nút cam DUY NHẤT của tab Cấu hình lương (các nút "+ Thêm…" đều ghost);
                thêm nút cam thứ hai là phá luật một-nút-cam-mỗi-màn. */}
            <Button
              variant="accent"
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
