// VIEW "VẤN ĐỀ" (Xung đột & Nguy cơ trễ) + gate Phát hành — view thứ 3 của bàn Xếp lịch, KHÔNG
// phải màn/route rời. Dẫn xuất từ backend (api.xepLich.vanDe + sanSangPhatHanh); mọi con số tính
// tại-chỗ. MÁY CHỈ GHI NHẬN: mọi "phương án" là LINK ĐIỀU HƯỚNG (đổi view/nhảy màn), KHÔNG auto-fix.
//
// Bố cục: SevBar (summary kiêm lọc mức) → danh sách vấn đề (list, gom theo group_key) → panel
// "Sẵn sàng phát hành" → dock đáy (chỉ 0 Chặn mới cho "Phát hành tất cả"). Drawer chi tiết tái dùng
// khung .khsx-scrim/.khsx-drawer--buoc; hành động xử lý (tiếp nhận · nhận · tạm hoãn · ngoại lệ · đã
// xử lý) nằm TRONG drawer — dòng list KHÔNG nhồi nút. Refetch sau mọi hành động (badge tự nhảy).
import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ApiError,
  api,
  type XepLichNguon,
  type XepLichSanSangItem,
  type XepLichSanSangOut,
  type XepLichSeverity,
  type XepLichVanDe,
  type XepLichVanDeListOut,
  type XepLichVanDeSummary,
} from "../api/client";
import { Icon, type IconName } from "../components/Icons";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import {
  BangLoi,
  CategoryChip,
  EmptyState,
  SevPill,
  VanDeTrangThaiPill,
  XEP_LICH_CATEGORY_META,
  XEP_LICH_SEV_META,
  ngay,
  thoiLuong,
} from "./keHoachSxShared";

// ============================ điều hướng "phương án" =========================
// Máy chỉ ghi nhận → phương án = ĐIỀU HƯỚNG. XepLichPage nhận union này và tự đổi view/nhảy màn.
export type PhuongAnNav =
  | { kind: "gantt-may" }
  | { kind: "bang-lenh"; flash?: { nguon: XepLichNguon; id: number } }
  | { kind: "bang-bai-ghep"; flash?: { nguon: XepLichNguon; id: number } }
  | { kind: "bang-ma"; ma: string }
  | { kind: "man-ke-hoach" };

const SEV_RANK: Record<XepLichSeverity, number> = { chan: 0, nghiem_trong: 1, cao: 2, canh_bao: 3 };

/** Bỏ dấu để tìm kiếm (bám norm của XepLichPage). */
const norm = (s: string): string =>
  s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d");

type ActMsg = { icon: IconName; label: string; nav: PhuongAnNav };

/** Câu mệnh lệnh + đích điều hướng theo loại vấn đề (Action Message). */
function phuongAnCho(it: XepLichVanDe): ActMsg[] {
  const lsx = it.impacts.lsx_ids[0];
  const bg = it.impacts.bai_ghep_ids[0];
  const out: ActMsg[] = [];
  switch (it.category) {
    case "trung_may":
    case "de_khoa_may":
      out.push({ icon: "calendar", label: "Mở Gantt máy để tìm khe trống", nav: { kind: "gantt-may" } });
      if (lsx != null) out.push({ icon: "clipboard", label: "Xem lệnh liên quan trong bảng", nav: { kind: "bang-lenh", flash: { nguon: "lsx", id: lsx } } });
      break;
    case "sai_tien_nhiem":
      out.push({ icon: "workflow", label: "Mở Bảng theo lệnh để sửa thứ tự công đoạn", nav: lsx != null ? { kind: "bang-lenh", flash: { nguon: "lsx", id: lsx } } : { kind: "bang-lenh" } });
      break;
    case "gang_thieu_xa_to":
      out.push({ icon: "layers", label: "Mở bài ghép để bổ sung công đoạn xả tờ", nav: bg != null ? { kind: "bang-bai-ghep", flash: { nguon: "in_ghep", id: bg } } : { kind: "bang-bai-ghep" } });
      break;
    case "thieu_du_lieu":
      out.push({ icon: "pencil", label: "Mở lệnh để khai năng suất / gán máy", nav: { kind: "man-ke-hoach" } });
      break;
    case "nguy_co_tre":
      out.push({ icon: "clock", label: "Mở Gantt máy để tìm khe sớm hơn", nav: { kind: "gantt-may" } });
      break;
    case "may_khong_kham":
      out.push({ icon: "printer", label: "Đổi sang máy phù hợp trong bảng", nav: lsx != null ? { kind: "bang-lenh", flash: { nguon: "lsx", id: lsx } } : { kind: "bang-lenh" } });
      break;
  }
  return out;
}

// ============================ view chính =====================================
export function VanDeView({
  data,
  sanSang,
  err,
  onRetry,
  token,
  canApprove,
  currentUserId,
  q,
  mayTen,
  onRefetch,
  onPhuongAn,
  onToast,
  onSetSearch,
}: {
  data: XepLichVanDeListOut | null;
  sanSang: XepLichSanSangOut | null;
  err: string | null;
  onRetry: () => void;
  token: string | null;
  canApprove: boolean;
  currentUserId: number | null;
  q: string;
  mayTen: (id: number) => string | null;
  onRefetch: () => void;
  onPhuongAn: (p: PhuongAnNav) => void;
  onToast: (text: string) => void;
  onSetSearch: (q: string) => void;
}) {
  const [sevFilter, setSevFilter] = useState<XepLichSeverity | null>(null);
  const [excFilter, setExcFilter] = useState(false);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [askReleaseAll, setAskReleaseAll] = useState(false);
  const [releaseBusy, setReleaseBusy] = useState(false);

  const items = useMemo(() => data?.items ?? [], [data]);
  const summary = data?.summary ?? null;

  // ---- lọc client-side (mức · ngoại lệ · tìm theo mã/mô tả) ----
  const filtered = useMemo(() => {
    const nq = norm(q.trim());
    return items.filter((it) => {
      if (sevFilter && it.severity !== sevFilter) return false;
      if (excFilter && it.trang_thai !== "ngoai_le") return false;
      if (nq && !norm(`${it.impacts.mas.join(" ")} ${it.title}`).includes(nq)) return false;
      return true;
    });
  }, [items, sevFilter, excFilter, q]);

  // ---- sắp xếp: mức desc → đơn-vị (group/lẻ) có tái-phát nổi lên → gom group_key → tái-phát trước ----
  const sorted = useMemo(() => {
    const groupMoLai = new Map<string, boolean>();
    for (const it of filtered) {
      if (it.group_key) groupMoLai.set(it.group_key, (groupMoLai.get(it.group_key) ?? false) || it.mo_lai);
    }
    const unitMoLai = (it: XepLichVanDe) => (it.group_key ? groupMoLai.get(it.group_key) ?? false : it.mo_lai);
    return [...filtered].sort((a, b) => {
      const sr = SEV_RANK[a.severity] - SEV_RANK[b.severity];
      if (sr !== 0) return sr;
      const um = (unitMoLai(a) ? 0 : 1) - (unitMoLai(b) ? 0 : 1);
      if (um !== 0) return um;
      const ga = a.group_key ?? `~${a.issue_key}`;
      const gb = b.group_key ?? `~${b.issue_key}`;
      if (ga !== gb) return ga < gb ? -1 : 1;
      const mo = (a.mo_lai ? 0 : 1) - (b.mo_lai ? 0 : 1);
      if (mo !== 0) return mo;
      return a.issue_key < b.issue_key ? -1 : a.issue_key > b.issue_key ? 1 : 0;
    });
  }, [filtered]);

  // ---- gom đơn-vị hiển thị: ≥2 cùng group_key → 1 nhóm; còn lại render lẻ ----
  const units = useMemo(() => {
    const out: ({ type: "group"; key: string; items: XepLichVanDe[] } | { type: "single"; item: XepLichVanDe })[] = [];
    let i = 0;
    while (i < sorted.length) {
      const it = sorted[i];
      if (it.group_key) {
        let j = i + 1;
        while (j < sorted.length && sorted[j].group_key === it.group_key) j++;
        if (j - i >= 2) { out.push({ type: "group", key: it.group_key, items: sorted.slice(i, j) }); i = j; continue; }
      }
      out.push({ type: "single", item: it });
      i++;
    }
    return out;
  }, [sorted]);

  // ---- drawer: tìm theo key trong data hiện tại; điều hướng prev/next theo thứ tự đang hiện ----
  const openIssue = openKey ? items.find((it) => it.issue_key === openKey) ?? null : null;
  const drawerIdx = openIssue ? sorted.findIndex((it) => it.issue_key === openIssue.issue_key) : -1;
  const goPrev = drawerIdx > 0 ? () => setOpenKey(sorted[drawerIdx - 1].issue_key) : undefined;
  const goNext = drawerIdx >= 0 && drawerIdx < sorted.length - 1 ? () => setOpenKey(sorted[drawerIdx + 1].issue_key) : undefined;

  // Vấn đề đã biến mất sau refetch (đã xử lý xong) → đóng drawer.
  useEffect(() => {
    if (openKey && !items.some((it) => it.issue_key === openKey)) setOpenKey(null);
  }, [items, openKey]);

  // ---- panel phát hành ----
  const releaseItems = useMemo(() => {
    const list = [...(sanSang?.items ?? [])];
    list.sort((a, b) => a.blocking - b.blocking || a.ma.localeCompare(b.ma, "vi"));
    return list;
  }, [sanSang]);
  const readyItems = releaseItems.filter((r) => r.blocking === 0);

  const doRelease = async (item: XepLichSanSangItem) => {
    if (!token) return;
    try {
      if (item.nguon === "lsx") await api.xepLich.phatHanhLsx(token, item.id);
      else await api.xepLich.phatHanhBaiGhep(token, item.id);
      onToast(`Đã phát hành ${item.ma}`);
      onRefetch();
    } catch (e: unknown) {
      onToast(e instanceof ApiError ? e.message : String(e));
    }
  };

  const doReleaseAll = async () => {
    if (!token || !readyItems.length) return;
    setReleaseBusy(true);
    try {
      for (const it of readyItems) {
        if (it.nguon === "lsx") await api.xepLich.phatHanhLsx(token, it.id);
        else await api.xepLich.phatHanhBaiGhep(token, it.id);
      }
      onToast(`Đã phát hành ${readyItems.length} kế hoạch`);
      onRefetch();
    } catch (e: unknown) {
      onToast(e instanceof ApiError ? e.message : String(e));
    } finally {
      setReleaseBusy(false);
      setAskReleaseAll(false);
    }
  };

  const showIssuesFor = (ma: string) => {
    setSevFilter(null);
    setExcFilter(false);
    onSetSearch(ma);
  };

  // ---- trạng thái tải / lỗi / rỗng ----
  if (err && !data) return <div className="xlcd-vwrap"><BangLoi text={err} onRetry={onRetry} /></div>;
  if (!data) return <ListSkeleton />;

  const chan = summary?.chan ?? 0;
  const tong = summary?.tong ?? 0;

  return (
    <div className="xlcd-vwrap">
      {tong === 0 ? (
        <EmptyState
          icon="shield"
          title="0 xung đột — kế hoạch sạch"
          sub="Không còn xung đột chặn hay nguy cơ trễ. Có thể phát hành các kế hoạch bên dưới."
        />
      ) : (
        <>
          {summary && (
            <SevBar
              summary={summary}
              sevFilter={sevFilter}
              excFilter={excFilter}
              onToggleSev={(s) => { setExcFilter(false); setSevFilter((cur) => (cur === s ? null : s)); }}
              onToggleExc={() => { setSevFilter(null); setExcFilter((v) => !v); }}
            />
          )}

          {sorted.length === 0 ? (
            <EmptyState
              icon="search"
              title="Không khớp bộ lọc"
              sub="Không có vấn đề nào khớp mức / từ khoá hiện tại."
              action={
                <Button variant="secondary" onClick={() => { setSevFilter(null); setExcFilter(false); onSetSearch(""); }}>
                  Xoá lọc
                </Button>
              }
            />
          ) : (
            <div className="xlcd-vlist">
              {units.map((u) =>
                u.type === "group" ? (
                  <VanDeGroup
                    key={u.key}
                    unit={u}
                    collapsed={collapsed.has(u.key)}
                    onToggle={() =>
                      setCollapsed((prev) => {
                        const next = new Set(prev);
                        next.has(u.key) ? next.delete(u.key) : next.add(u.key);
                        return next;
                      })
                    }
                    mayTen={mayTen}
                    currentUserId={currentUserId}
                    onOpen={setOpenKey}
                  />
                ) : (
                  <VanDeRow
                    key={u.item.issue_key}
                    it={u.item}
                    mayTen={mayTen}
                    currentUserId={currentUserId}
                    onOpen={() => setOpenKey(u.item.issue_key)}
                  />
                ),
              )}
            </div>
          )}
        </>
      )}

      <ReleasePanel
        items={releaseItems}
        canApprove={canApprove}
        onRelease={doRelease}
        onShowIssues={showIssuesFor}
      />

      {(chan > 0 || readyItems.length > 0) && (
        <ReleaseDock
          chan={chan}
          readyCount={readyItems.length}
          canApprove={canApprove}
          onReleaseAll={() => setAskReleaseAll(true)}
        />
      )}

      {openIssue && (
        <DrawerVanDe
          it={openIssue}
          groupSize={openIssue.group_key ? items.filter((x) => x.group_key === openIssue.group_key).length : 0}
          token={token}
          canApprove={canApprove}
          currentUserId={currentUserId}
          mayTen={mayTen}
          hasPrev={!!goPrev}
          hasNext={!!goNext}
          onPrev={goPrev}
          onNext={goNext}
          onClose={() => setOpenKey(null)}
          onDone={onRefetch}
          onToast={onToast}
          onPhuongAn={onPhuongAn}
          onShowGroup={() => { setSevFilter(null); setExcFilter(false); onSetSearch(""); setOpenKey(null); }}
        />
      )}

      <ConfirmDialog
        open={askReleaseAll}
        title={`Phát hành ${readyItems.length} kế hoạch?`}
        message="Các lệnh / bài ghép sạch xung đột chặn sẽ được phát hành xuống xưởng. Việc này khoá chỉnh sửa lịch của chúng."
        confirmLabel="Phát hành tất cả"
        busy={releaseBusy}
        onConfirm={doReleaseAll}
        onCancel={() => setAskReleaseAll(false)}
      />
    </div>
  );
}

// ============================ summary bar (kiêm lọc mức) =====================
function SevBar({
  summary, sevFilter, excFilter, onToggleSev, onToggleExc,
}: {
  summary: XepLichVanDeSummary;
  sevFilter: XepLichSeverity | null;
  excFilter: boolean;
  onToggleSev: (s: XepLichSeverity) => void;
  onToggleExc: () => void;
}) {
  const levels: XepLichSeverity[] = ["chan", "nghiem_trong", "cao", "canh_bao"];
  const chan = summary.chan;
  const tong = summary.tong;
  return (
    <div className="xlcd-sevbar" role="group" aria-label="Lọc theo mức nghiêm trọng">
      <div className="xlcd-sevbar__stats">
        {levels.map((s) => {
          const n = summary[s];
          const meta = XEP_LICH_SEV_META[s];
          const active = sevFilter === s;
          const isChan = s === "chan";
          return (
            <button
              key={s}
              type="button"
              aria-pressed={active}
              className={`xlcd-sevstat ${meta.cls} ${active ? "is-active" : ""} ${n === 0 ? "is-zero" : ""} ${isChan && n > 0 ? "is-blocking" : ""}`}
              onClick={() => onToggleSev(s)}
            >
              <span className="xlcd-sevstat__n">{n}</span>
              <span className="xlcd-sevstat__lb">{meta.label}</span>
              {isChan && n > 0 && <span className="xlcd-sevstat__micro">chưa phát hành được</span>}
            </button>
          );
        })}
        <button
          type="button"
          aria-pressed={excFilter}
          className={`xlcd-sevstat xlcd-sevstat--exc ${excFilter ? "is-active" : ""} ${summary.ngoai_le === 0 ? "is-zero" : ""}`}
          onClick={onToggleExc}
        >
          <span className="xlcd-sevstat__n">{summary.ngoai_le}</span>
          <span className="xlcd-sevstat__lb"><Icon name="shield" size={12} /> Ngoại lệ</span>
        </button>
      </div>
      <p className={`xlcd-sevbar__status ${chan > 0 ? "is-bad" : "is-ok"}`}>
        {chan > 0 ? (
          <><Icon name="ban" size={13} /> Chưa phát hành được — còn {chan} xung đột chặn</>
        ) : (
          <><Icon name="check" size={13} /> Không còn xung đột chặn — sẵn sàng phát hành</>
        )}
        {tong > 0 && <span className="xlcd-sevbar__tong">· {tong} vấn đề</span>}
      </p>
    </div>
  );
}

// ============================ nhóm "cùng nguyên nhân" ========================
function VanDeGroup({
  unit, collapsed, onToggle, mayTen, currentUserId, onOpen,
}: {
  unit: { type: "group"; key: string; items: XepLichVanDe[] };
  collapsed: boolean;
  onToggle: () => void;
  mayTen: (id: number) => string | null;
  currentUserId: number | null;
  onOpen: (key: string) => void;
}) {
  const head = unit.items[0];
  const meta = XEP_LICH_CATEGORY_META[head.category];
  return (
    <div className="xlcd-vgroup">
      <button type="button" className="xlcd-vgroup__head" aria-expanded={!collapsed} onClick={onToggle}>
        <Icon name="chevron" size={14} className={collapsed ? "xlcd-vgroup__caret is-collapsed" : "xlcd-vgroup__caret"} />
        <Icon name={meta.icon} size={13} />
        <span className="xlcd-vgroup__label">Cùng nguyên nhân: {meta.label}</span>
        <span className="xlcd-vgroup__n">{unit.items.length} vấn đề</span>
      </button>
      {!collapsed && unit.items.map((it) => (
        <VanDeRow key={it.issue_key} it={it} mayTen={mayTen} currentUserId={currentUserId} onOpen={() => onOpen(it.issue_key)} grouped />
      ))}
    </div>
  );
}

// ============================ 1 dòng vấn đề ==================================
function VanDeRow({
  it, mayTen, currentUserId, onOpen, grouped = false,
}: {
  it: XepLichVanDe;
  mayTen: (id: number) => string | null;
  currentUserId: number | null;
  onOpen: () => void;
  grouped?: boolean;
}) {
  const sevCls = XEP_LICH_SEV_META[it.severity].cls;
  const mas = it.impacts.mas;
  const masShown = mas.slice(0, 3);
  const masMore = mas.length - masShown.length;
  const mayNames = it.impacts.may_ids.map((id) => mayTen(id)).filter((x): x is string => !!x);
  const hasException = it.exception != null;

  return (
    <button
      type="button"
      className={`xlcd-vrow ${sevCls} ${grouped ? "xlcd-vrow--grouped" : ""} ${hasException ? "xlcd-vrow--exc" : ""}`}
      onClick={onOpen}
      aria-label={`Mở vấn đề: ${it.title}`}
    >
      <div className="xlcd-vrow__main">
        <div className="xlcd-vrow__top">
          <SevPill sev={it.severity} />
          <CategoryChip category={it.category} />
          <span className="xlcd-vrow__title">{it.title}</span>
        </div>
        <div className="xlcd-vrow__meta">
          {masShown.map((m) => <span key={m} className="xlcd-vma">{m}</span>)}
          {masMore > 0 && <span className="xlcd-vma xlcd-vma--more">+{masMore}</span>}
          {mayNames.length > 0 && (
            <span className="xlcd-vrow__may">· {mayNames[0]}{mayNames.length > 1 ? ` +${mayNames.length - 1}` : ""}</span>
          )}
          {it.delay_phut != null && it.delay_phut > 0 && (
            <span className="xlcd-vdelay"><Icon name="clock" size={11} /> ~{thoiLuong(it.delay_phut)}</span>
          )}
        </div>
      </div>
      <div className="xlcd-vrow__side">
        {it.mo_lai && (
          <span className="xlcd-vflag xlcd-vflag--repeat"><Icon name="activity" size={11} /> Tái phát</span>
        )}
        {hasException && (
          <span className="xlcd-vflag xlcd-vflag--exc">
            <Icon name="shield" size={11} /> Ngoại lệ{it.exception?.expires_at ? ` · đến ${ngay(it.exception.expires_at)}` : ""}
          </span>
        )}
        <VanDeTrangThaiPill tt={it.trang_thai} />
        {it.assigned_to != null && (
          <span className="xlcd-vwho">
            <Icon name="users" size={11} /> {it.assigned_to === currentUserId ? "Bạn" : "Đã giao"}
          </span>
        )}
      </div>
    </button>
  );
}

// ============================ drawer chi tiết vấn đề =========================
function DrawerVanDe({
  it, groupSize, token, canApprove, currentUserId, mayTen, hasPrev, hasNext, onPrev, onNext, onClose, onDone, onToast, onPhuongAn, onShowGroup,
}: {
  it: XepLichVanDe;
  groupSize: number;
  token: string | null;
  canApprove: boolean;
  currentUserId: number | null;
  mayTen: (id: number) => string | null;
  hasPrev: boolean;
  hasNext: boolean;
  onPrev?: () => void;
  onNext?: () => void;
  onClose: () => void;
  onDone: () => void;
  onToast: (text: string) => void;
  onPhuongAn: (p: PhuongAnNav) => void;
  onShowGroup: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(it.note ?? "");
  const [excOpen, setExcOpen] = useState(false);
  const [excLyDo, setExcLyDo] = useState("");
  const [excExpires, setExcExpires] = useState("");

  useEffect(() => {
    setNote(it.note ?? "");
    setExcOpen(false); setExcLyDo(""); setExcExpires("");
  }, [it.issue_key, it.note]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const run = async (fn: () => Promise<unknown>, okMsg: string) => {
    if (!token || busy) return;
    setBusy(true);
    try { await fn(); onToast(okMsg); onDone(); }
    catch (e: unknown) { onToast(e instanceof ApiError ? e.message : String(e)); }
    finally { setBusy(false); }
  };

  const isChan = it.severity === "chan";
  const mayNames = it.impacts.may_ids.map((id) => mayTen(id)).filter((x): x is string => !!x);
  const acts = phuongAnCho(it);
  const canException = canApprove && it.category !== "may_khong_kham" && it.exception == null;
  const nav = (p: PhuongAnNav) => { onClose(); onPhuongAn(p); };

  return (
    <div className="khsx-scrim" onClick={onClose}>
      <div className="khsx-drawer khsx-drawer--buoc" role="dialog" aria-modal="true" aria-label="Chi tiết vấn đề kế hoạch" onClick={(e) => e.stopPropagation()}>
        <div className="khsx-drawer__head">
          <div className="khsx-drawer__headmain">
            <p className="khsx-drawer__kicker">Vấn đề kế hoạch</p>
            <h2 className="khsx-drawer__title">{it.title}</h2>
            <p className="khsx-drawer__meta xlcd-vd-metarow">
              <SevPill sev={it.severity} />
              <CategoryChip category={it.category} />
            </p>
          </div>
          <div className="khsx-buoc__nav">
            <button type="button" disabled={!hasPrev} onClick={onPrev} aria-label="Vấn đề trước"><Icon name="chevron" size={16} /></button>
            <button type="button" disabled={!hasNext} onClick={onNext} aria-label="Vấn đề sau"><Icon name="chevron" size={16} /></button>
          </div>
          <button type="button" className="khsx-drawer__x" onClick={onClose} aria-label="Đóng"><Icon name="x" size={18} /></button>
        </div>

        <div className="khsx-drawer__body">
          {/* 1 · băng mức */}
          {isChan ? (
            <div className="khsx-ready khsx-ready--blocked">
              <p className="khsx-ready__title"><Icon name="ban" size={15} /> Vấn đề này CHẶN phát hành</p>
              <p className="xlcd-vd-blocktext">Phải xử lý (hoặc duyệt ngoại lệ) thì lệnh / bài ghép liên quan mới phát hành được.</p>
            </div>
          ) : (
            <p className={`khsx-callout ${it.severity === "canh_bao" ? "khsx-callout--steel" : "khsx-callout--amber"}`}>
              <Icon name="help" size={16} /> Không chặn phát hành — cần lưu ý và xử lý sớm để tránh trễ.
            </p>
          )}

          {/* 2 · nguyên nhân gốc */}
          <div className="khsx-nhom">
            <h3 className="khsx-nhom__title">Nguyên nhân</h3>
            <p className="xlcd-vd-cause">{it.nguyen_nhan ?? "—"}</p>
            {it.group_key && groupSize > 1 && (
              <button type="button" className="khsx-xlink xlcd-vd-grouplink" onClick={onShowGroup}>
                Cùng nguyên nhân với {groupSize - 1} vấn đề khác — xem nhóm trong danh sách
              </button>
            )}
          </div>

          {/* 3 · đối tượng ảnh hưởng */}
          <div className="khsx-nhom">
            <h3 className="khsx-nhom__title">Đối tượng ảnh hưởng</h3>
            <div className="xlcd-vd-objs">
              {it.impacts.mas.length === 0 ? (
                <span className="khsx-muted">—</span>
              ) : (
                it.impacts.mas.map((m) => (
                  <button key={m} type="button" className="khsx-xlink xlcd-vd-ma" onClick={() => nav({ kind: "bang-ma", ma: m })}>
                    {m}
                  </button>
                ))
              )}
            </div>
            <p className="xlcd-vd-objmeta">
              {mayNames.length > 0 && <span><Icon name="printer" size={12} /> {mayNames.join(", ")}</span>}
              {it.impacts.dong_ids.length > 0 && <span><Icon name="clipboard" size={12} /> {it.impacts.dong_ids.length} dòng lịch</span>}
            </p>
          </div>

          {/* 4 · dòng thời gian */}
          {it.delay_phut != null && it.delay_phut > 0 && (
            <p className="khsx-callout khsx-callout--amber xlcd-vd-delay">
              <Icon name="clock" size={16} /> Đẩy trễ ~{thoiLuong(it.delay_phut)} so với mốc dự kiến.
            </p>
          )}

          {/* 5 · phương án đề xuất (điều hướng — không auto-fix) */}
          {acts.length > 0 && (
            <div className="khsx-nhom">
              <h3 className="khsx-nhom__title">Phương án đề xuất</h3>
              <p className="khsx-nhom__sub">Máy chỉ gợi ý — người kế hoạch quyết. Bấm để đi tới đúng chỗ chỉnh.</p>
              <div className="xlcd-actmsg-list">
                {acts.map((a, k) => (
                  <button key={k} type="button" className="xlcd-actmsg" onClick={() => nav(a.nav)}>
                    <Icon name={a.icon} size={15} />
                    <span>{a.label}</span>
                    <Icon name="chevron" size={14} className="xlcd-actmsg__go" />
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* ngoại lệ đã duyệt */}
          {it.exception && (
            <p className="khsx-callout khsx-callout--steel xlcd-vd-excbadge">
              <Icon name="shield" size={16} />
              <span>
                Đã duyệt ngoại lệ{it.exception.expires_at ? ` · hạn đến ${ngay(it.exception.expires_at)}` : " · vô thời hạn"}.
                {it.exception.ly_do ? ` Lý do: ${it.exception.ly_do}` : ""}
              </span>
            </p>
          )}

          {/* ghi chú xử lý */}
          <div className="khsx-nhom">
            <h3 className="khsx-nhom__title">Ghi chú xử lý</h3>
            <textarea
              className="xlcd-vd-note"
              rows={2}
              value={note}
              placeholder="Ghi chú cho người xử lý…"
              onChange={(e) => setNote(e.target.value)}
            />
            <div className="xlcd-vd-noterow">
              <Button variant="secondary" disabled={busy || note === (it.note ?? "")} onClick={() => run(() => api.xepLich.vanDeGhiChu(token!, it.issue_key, note.trim()), "Đã lưu ghi chú")}>
                Lưu ghi chú
              </Button>
            </div>
          </div>
        </div>

        {/* foot: hành động xử lý */}
        <div className="khsx-drawer__foot xlcd-vd-foot">
          <div className="xlcd-vd-foot__l">
            {it.trang_thai === "moi" && (
              <Button variant="secondary" disabled={busy} onClick={() => run(() => api.xepLich.vanDeTiepNhan(token!, it.issue_key), "Đã tiếp nhận")}>
                Tiếp nhận
              </Button>
            )}
            {it.assigned_to === currentUserId && currentUserId != null ? (
              <span className="xlcd-vd-mine"><Icon name="check" size={13} /> Bạn đang xử lý</span>
            ) : currentUserId != null ? (
              <Button variant="secondary" disabled={busy} onClick={() => run(() => api.xepLich.vanDeGiao(token!, it.issue_key, currentUserId), "Đã nhận việc")}>
                Nhận cho tôi
              </Button>
            ) : null}
            <Button variant="ghost" disabled={busy} onClick={() => run(() => api.xepLich.vanDeTamHoan(token!, it.issue_key), "Đã tạm hoãn")}>
              Tạm hoãn
            </Button>
          </div>
          <div className="xlcd-vd-foot__r">
            {canException && (
              <Button variant="secondary" disabled={busy} onClick={() => setExcOpen(true)}>
                <Icon name="shield" size={14} /> Xin ngoại lệ
              </Button>
            )}
            <Button variant="primary" disabled={busy} onClick={() => run(() => api.xepLich.vanDeDanhDauXuLy(token!, it.issue_key), "Đã đánh dấu xử lý")}>
              <Icon name="check" size={14} /> Đánh dấu đã xử lý
            </Button>
          </div>
        </div>
      </div>

      {/* dialog duyệt ngoại lệ */}
      <ConfirmDialog
        open={excOpen}
        title="Duyệt ngoại lệ cho vấn đề này?"
        message="Ngoại lệ cho phép phát hành dù còn vấn đề. Ghi rõ lý do — sẽ lưu vào nhật ký."
        confirmLabel="Duyệt ngoại lệ"
        confirmDisabled={excLyDo.trim() === ""}
        onConfirm={() =>
          run(
            () => api.xepLich.vanDeNgoaiLe(token!, it.issue_key, excLyDo.trim(), excExpires ? `${excExpires}:00` : null),
            "Đã duyệt ngoại lệ",
          ).then(() => setExcOpen(false))
        }
        onCancel={() => setExcOpen(false)}
      >
        <div className="xlcd-vd-excform">
          <label className="khsx-field">
            <span className="khsx-field__label">Lý do ngoại lệ</span>
            <input value={excLyDo} onChange={(e) => setExcLyDo(e.target.value)} placeholder="Vì sao chấp nhận phát hành dù còn vấn đề" autoFocus />
          </label>
          <label className="khsx-field">
            <span className="khsx-field__label">Hết hạn (tuỳ chọn)</span>
            <input type="datetime-local" value={excExpires} onChange={(e) => setExcExpires(e.target.value)} />
          </label>
        </div>
      </ConfirmDialog>
    </div>
  );
}

// ============================ panel "Sẵn sàng phát hành" =====================
function ReleasePanel({
  items, canApprove, onRelease, onShowIssues,
}: {
  items: XepLichSanSangItem[];
  canApprove: boolean;
  onRelease: (item: XepLichSanSangItem) => void;
  onShowIssues: (ma: string) => void;
}) {
  return (
    <section className="xlcd-release" aria-label="Sẵn sàng phát hành">
      <h3 className="xlcd-release__title">
        <Icon name="send" size={15} /> Sẵn sàng phát hành
        <span className="xlcd-release__count">{items.length}</span>
      </h3>
      {items.length === 0 ? (
        <p className="xlcd-release__empty">Chưa có lệnh / bài ghép nào ở trạng thái đã lập kế hoạch.</p>
      ) : (
        <ul className="xlcd-release__list">
          {items.map((it) => (
            <li key={`${it.nguon}-${it.id}`} className="xlcd-release__row">
              <span className="xlcd-release__ma">
                <Icon name={it.nguon === "in_ghep" ? "layers" : "clipboard"} size={13} />
                {it.ma}
              </span>
              {it.blocking === 0 ? (
                <Button variant="primary" disabled={!canApprove} onClick={() => onRelease(it)} title={canApprove ? undefined : "Cần quyền phát hành"}>
                  <Icon name="send" size={13} /> Phát hành
                </Button>
              ) : (
                <span className="xlcd-release__blocked">
                  <span className="xlcd-release__chan"><Icon name="ban" size={12} /> còn {it.blocking} chặn</span>
                  <button type="button" className="khsx-xlink" onClick={() => onShowIssues(it.ma)}>xem vấn đề</button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ============================ dock đáy phát hành =============================
function ReleaseDock({
  chan, readyCount, canApprove, onReleaseAll,
}: {
  chan: number;
  readyCount: number;
  canApprove: boolean;
  onReleaseAll: () => void;
}) {
  if (chan > 0) {
    return (
      <div className="xlcd-bulk xlcd-release-dock xlcd-release-dock--wait" role="status">
        <span className="xlcd-release-dock__msg">
          <Icon name="ban" size={15} /> Còn {chan} xung đột chặn — chưa phát hành được
        </span>
      </div>
    );
  }
  return (
    <div className="xlcd-bulk xlcd-release-dock" role="region" aria-label="Phát hành kế hoạch">
      <span className="xlcd-release-dock__msg">
        <Icon name="check" size={15} /> Kế hoạch sạch xung đột chặn — {readyCount} sẵn sàng
      </span>
      <div className="xlcd-release-dock__sp" />
      <Button variant="accent" disabled={!canApprove || readyCount === 0} onClick={onReleaseAll}>
        <Icon name="send" size={14} /> Phát hành tất cả ({readyCount})
      </Button>
    </div>
  );
}

// ============================ skeleton =======================================
function ListSkeleton(): ReactNode {
  return (
    <div className="xlcd-vwrap">
      <div className="xlcd-sevbar xlcd-sevbar--skel">
        {Array.from({ length: 5 }).map((_, i) => <span key={i} className="khsx-skel__bar xlcd-sevstat--skel" />)}
      </div>
      <div className="xlcd-vlist">
        {Array.from({ length: 5 }).map((_, i) => <span key={i} className="khsx-skel__bar xlcd-vrow--skel" />)}
      </div>
    </div>
  );
}
