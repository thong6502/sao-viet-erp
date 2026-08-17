import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  api,
  BAI_GHEP_CANH_BAO_LABELS,
  BAI_GHEP_THIEU_LABELS,
  type BaiGhep2Detail,
  type BaiGhep2Activity,
  type BaiGhep2ListItem,
  type BaiGhep2NguoiPhuTrachOption,
  type BaiGhep2UpdateBody,
  type BaiGhep2VatTuHieuLuc,
  type BaiGhepBuocChungBody,
  type BaiGhepSoDo,
  type BaiGhepSoDoBuocChung,
  type HangChoGhepItem,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { BaiGhepDagCanvas } from "../components/BaiGhepDagCanvas";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Icon } from "../components/Icons";
import { BuocChungForm } from "./BaiGhepBuocChungForm";
import {
  BangLoi,
  ChipGap,
  EmptyState,
  Skeleton,
  TrangThaiPill,
  classHan,
  ngay,
  ngayGio,
  num,
} from "./keHoachSxShared";
import {
  BAI_GHEP_2_TABS,
  coTheTaoBai,
  giuLuaChonSauTai,
  quyetDinhRealtime,
  type BaiGhep2TabKey,
} from "./baiGhep2Rules";
import "./ke-hoach-sx.css";
import "./bai-ghep-2.css";

type View = { mode: "list" } | { mode: "detail"; id: number };

function loi(e: unknown): string {
  return e instanceof ApiError ? e.message : String(e);
}

export function BaiGhep2Page({
  navigate,
  eventTick,
  onBadgeStale,
}: {
  navigate?: (id: string, params?: Record<string, unknown>) => void;
  eventTick?: number;
  onBadgeStale?: () => void;
}) {
  const { token } = useAuth();
  const canCreate = useCan()("bai_ghep_2", "create");
  const [view, setView] = useState<View>({ mode: "list" });
  const [tab, setTab] = useState<"cho" | "list">("cho");
  const [pool, setPool] = useState<HangChoGhepItem[] | null>(null);
  const [list, setList] = useState<BaiGhep2ListItem[] | null>(null);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [q, setQ] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const loadPool = useCallback(() => {
    if (!token) return;
    api.baiGhep2.hangCho(token, { q: q.trim() || undefined })
      .then((r) => {
        setPool(r.items);
        setPicked((old) => giuLuaChonSauTai(old, r.items.map((x) => x.lsx_id), q));
      })
      .catch((e: unknown) => setErr(loi(e)));
  }, [q, token]);

  const loadList = useCallback(() => {
    if (!token) return;
    api.baiGhep2.list(token).then((r) => setList(r.items)).catch((e: unknown) => setErr(loi(e)));
  }, [token]);

  const reload = useCallback(() => {
    loadPool();
    loadList();
    onBadgeStale?.();
  }, [loadList, loadPool, onBadgeStale]);

  useEffect(() => {
    const timer = setTimeout(loadPool, q ? 250 : 0);
    return () => clearTimeout(timer);
  }, [eventTick, loadPool, q]);
  useEffect(() => loadList(), [eventTick, loadList]);

  async function tao() {
    if (!token || !coTheTaoBai(picked)) return;
    setCreating(true);
    setErr(null);
    try {
      const d = await api.baiGhep2.tao(token, [...picked]);
      setPicked(new Set());
      reload();
      setView({ mode: "detail", id: d.id });
    } catch (e) {
      setErr(loi(e));
    } finally {
      setCreating(false);
    }
  }

  if (view.mode === "detail") {
    return (
      <main className="khsx bg2">
        <BaiGhep2Detail
          id={view.id}
          eventTick={eventTick}
          navigate={navigate}
          onBack={() => setView({ mode: "list" })}
          onChanged={reload}
        />
      </main>
    );
  }

  return (
    <main className="khsx bg2">
      <header className="khsx__head">
        <p className="eyebrow">Sản xuất</p>
        <div className="khsx__headrow">
          <h1 className="khsx__title">Bài ghép 2</h1>
          <span className="khsx__count">
            {num(pool?.length ?? 0)} lệnh chờ ghép · {num(list?.length ?? 0)} bài ghép
          </span>
        </div>
      </header>

      <div className="khsx__segrow" role="tablist" aria-label="Khu vực Bài ghép 2">
        <button type="button" role="tab" aria-selected={tab === "cho"}
          className={`seg ${tab === "cho" ? "is-active" : ""}`} onClick={() => setTab("cho")}>
          Lệnh chờ ghép <span className="chip-count chip-count--alert">{pool?.length ?? 0}</span>
        </button>
        <button type="button" role="tab" aria-selected={tab === "list"}
          className={`seg ${tab === "list" ? "is-active" : ""}`} onClick={() => setTab("list")}>
          Bài ghép <span className="chip-count">{list?.length ?? 0}</span>
        </button>
      </div>

      {err && <BangLoi text={err} onRetry={reload} />}
      {tab === "cho" ? (
        <section aria-label="Danh sách lệnh chờ ghép">
          <div className="khsx__toolbar">
            <label className="khsx__search">
              <Icon name="search" size={15} />
              <input type="search" value={q} onChange={(e) => setQ(e.target.value)}
                placeholder="Tìm mã / tên lệnh…" aria-label="Tìm lệnh chờ ghép" />
            </label>
            <span className="khsx__spacer" />
            <span className="bg2__picked" aria-live="polite">{picked.size} lệnh đã chọn</span>
            <Button variant="accent" disabled={!canCreate || !coTheTaoBai(picked) || creating}
              loading={creating} onClick={tao}>
              Tạo bài ghép{picked.size ? ` (${picked.size})` : ""}
            </Button>
          </div>
          <QueueTable rows={pool} picked={picked} onToggle={(id) => setPicked((old) => {
            const next = new Set(old);
            next.has(id) ? next.delete(id) : next.add(id);
            return next;
          })} />
        </section>
      ) : (
        <GangList rows={list} onOpen={(id) => setView({ mode: "detail", id })} />
      )}
    </main>
  );
}

function QueueTable({ rows, picked, onToggle }: {
  rows: HangChoGhepItem[] | null;
  picked: ReadonlySet<number>;
  onToggle: (id: number) => void;
}) {
  return (
    <div className="khsx__tablewrap">
      <table className="khsx__table khsx__table--queue">
        <thead><tr><th aria-label="Chọn" /><th>Lệnh</th><th>Giấy</th><th>Mực in</th><th>Khổ TP</th><th className="khsx-num">Số lượng</th><th>Hạn in</th></tr></thead>
        {rows == null ? <Skeleton rows={5} cols={7} /> : rows.length === 0 ? (
          <tbody><tr><td colSpan={7}><EmptyState icon="layers" title="Không có lệnh chờ ghép"
            sub="Các lệnh đủ điều kiện sẽ tự xuất hiện tại đây." /></td></tr></tbody>
        ) : (
          <tbody>{rows.map((r) => {
            const checked = picked.has(r.lsx_id);
            return (
              <tr key={r.lsx_id} className={`khsx__row ${checked ? "bg2__row--picked" : ""}`}
                onClick={() => onToggle(r.lsx_id)}>
                <td><input type="checkbox" checked={checked} onChange={() => onToggle(r.lsx_id)}
                  onClick={(e) => e.stopPropagation()} aria-label={`Chọn ${r.ma}`} /></td>
                <td><div className="khsx__code">{r.ma}</div><div className="khsx__name">{r.ten || "—"} {r.is_rush && <ChipGap />}</div><div className="khsx__sub">{r.customer_name}</div></td>
                <td>{r.giay_ten || "—"}{r.gsm ? <span className="khsx-unit"> · {r.gsm} gsm</span> : null}</td>
                <td>{r.so_mau_a ?? 0}/{r.so_mau_b ?? 0}</td><td>{r.kho_tp || "—"}</td>
                <td className="khsx-num">{num(r.so_luong_dat)} <span className="khsx-unit">{r.don_vi_tinh}</span></td>
                <td className={classHan(r.han_hoan_thanh_sx)}>{ngay(r.han_hoan_thanh_sx)}</td>
              </tr>
            );
          })}</tbody>
        )}
      </table>
    </div>
  );
}

function GangList({ rows, onOpen }: { rows: BaiGhep2ListItem[] | null; onOpen: (id: number) => void }) {
  return (
    <div className="khsx__tablewrap">
      <table className="khsx__table khsx__table--lenh">
        <thead><tr><th>Bài ghép</th><th>Số lệnh</th><th className="khsx-num">Tờ chạy</th><th>Hạn</th><th>Trạng thái</th></tr></thead>
        {rows == null ? <Skeleton rows={4} cols={5} /> : rows.length === 0 ? (
          <tbody><tr><td colSpan={5}><EmptyState icon="layers" title="Chưa có bài ghép"
            sub="Chọn ít nhất hai lệnh ở hàng chờ để bắt đầu." /></td></tr></tbody>
        ) : <tbody>{rows.map((r) => (
          <tr key={r.id} className="khsx__row" role="button" tabIndex={0} onClick={() => onOpen(r.id)}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onOpen(r.id))}>
            <td><div className="khsx__code">{r.ma}</div><div className="khsx__name">{r.ten || `Bài ghép ${r.ma}`}</div></td>
            <td>{r.so_lsx}</td><td className="khsx-num">{num(r.so_to_tot)}</td>
            <td className={classHan(r.han_hoan_thanh_sx)}>{ngay(r.han_hoan_thanh_sx)}</td>
            <td><TrangThaiPill tt={r.trang_thai} /> {r.is_rush && <ChipGap />}</td>
          </tr>
        ))}</tbody>}
      </table>
    </div>
  );
}

type MetaForm = BaiGhep2UpdateBody & { ten: string; is_rush: boolean };
const toForm = (d: BaiGhep2Detail): MetaForm => ({
  ten: d.ten,
  han_hoan_thanh_sx: d.han_hoan_thanh_sx,
  is_rush: d.is_rush,
  nguoi_phu_trach_id: d.nguoi_phu_trach_id,
  ghi_chu: d.ghi_chu ?? "",
  giay_id: d.giay_id,
  kho_in_dai: d.kho_in_dai,
  kho_in_rong: d.kho_in_rong,
  hao_hut_setup: d.hao_hut_setup,
  hao_hut_chay: d.hao_hut_chay,
});

function BaiGhep2Detail({ id, eventTick, onBack, onChanged, navigate }: {
  id: number;
  eventTick?: number;
  onBack: () => void;
  onChanged: () => void;
  navigate?: (id: string, params?: Record<string, unknown>) => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canUpdate = can("bai_ghep_2", "update");
  const canDelete = can("bai_ghep_2", "delete");
  const [tab, setTab] = useState<BaiGhep2TabKey>("chung");
  const [d, setD] = useState<BaiGhep2Detail | null>(null);
  const [form, setForm] = useState<MetaForm | null>(null);
  const [sd, setSd] = useState<BaiGhepSoDo | null>(null);
  const [materials, setMaterials] = useState<BaiGhep2VatTuHieuLuc | null>(null);
  const [activity, setActivity] = useState<BaiGhep2Activity[] | null>(null);
  const [owners, setOwners] = useState<BaiGhep2NguoiPhuTrachOption[]>([]);
  const [drawer, setDrawer] = useState<BaiGhepSoDoBuocChung | null>(null);
  const [memberPicker, setMemberPicker] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [stale, setStale] = useState(false);
  const dirtyRef = useRef(false);
  const eventRef = useRef(eventTick);
  const dialogRef = useRef<HTMLElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const [detail, diagram, ownerOptions] = await Promise.all([
        api.baiGhep2.get(token, id),
        api.baiGhep2.soDo(token, id),
        api.baiGhep2.nguoiPhuTrachOptions(token),
      ]);
      setD(detail); setForm(toForm(detail)); setSd(diagram); setOwners(ownerOptions.items); setErr(null);
    } catch (e) { setErr(loi(e)); }
  }, [id, token]);
  const loadMaterials = useCallback(() => {
    if (!token) return Promise.resolve();
    return api.baiGhep2.vatTuHieuLuc(token, id).then(setMaterials).catch((e: unknown) => setErr(loi(e)));
  }, [id, token]);
  const loadActivity = useCallback(() => {
    if (!token) return Promise.resolve();
    return api.baiGhep2.activity(token, id).then((r) => setActivity(r.items)).catch((e: unknown) => setErr(loi(e)));
  }, [id, token]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (tab === "vattu") void loadMaterials();
  }, [loadMaterials, tab]);
  useEffect(() => {
    if (tab === "nhatky") void loadActivity();
  }, [loadActivity, tab]);

  const dirty = useMemo(() => d && form && JSON.stringify(toForm(d)) !== JSON.stringify(form), [d, form]);
  useEffect(() => { dirtyRef.current = Boolean(dirty); }, [dirty]);
  useEffect(() => {
    if (!drawer && !memberPicker) return;
    returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        // Confirm tách bước là dialog con; để chính nó xử lý Esc, không đóng luôn drawer cha.
        if (document.querySelector(".cdlg-overlay")) return;
        setDrawer(null);
        setMemberPicker(false);
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
      )];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("keydown", close);
      returnFocusRef.current?.focus();
    };
  }, [drawer, memberPicker]);
  useEffect(() => {
    if (eventTick === eventRef.current) return;
    eventRef.current = eventTick;
    const action = quyetDinhRealtime(dirtyRef.current, tab);
    if (action.stale) { setStale(true); return; }
    void load();
    if (action.refresh.includes("vattu")) void loadMaterials();
    if (action.refresh.includes("nhatky")) void loadActivity();
  }, [eventTick, load, loadActivity, loadMaterials, tab]);
  const apply = useCallback((next: BaiGhep2Detail) => {
    setD(next); setForm(toForm(next)); setStale(false); onChanged();
    if (token) {
      api.baiGhep2.soDo(token, id).then(setSd).catch((e: unknown) => setErr(loi(e)));
      if (tab === "vattu") api.baiGhep2.vatTuHieuLuc(token, id).then(setMaterials).catch((e: unknown) => setErr(loi(e)));
    }
  }, [id, onChanged, tab, token]);

  async function mutate(work: () => Promise<BaiGhep2Detail>): Promise<boolean> {
    setErr(null);
    try { apply(await work()); return true; } catch (e) { setErr(loi(e)); return false; }
  }

  async function save() {
    if (!token || !form) return;
    setSaving(true);
    try { await mutate(() => api.baiGhep2.update(token, id, form)); } finally { setSaving(false); }
  }

  async function group(stepKeys: string[]) {
    if (!token) return;
    const before = new Set(sd?.gop.map((g) => g.step_key) ?? []);
    if (!await mutate(() => api.baiGhep2.gop(token, id, stepKeys))) return;
    const next = await api.baiGhep2.soDo(token, id);
    setSd(next);
    setDrawer(next.gop.find((g) => !before.has(g.step_key)) ?? null);
  }

  if (err && !d) return <BangLoi text={err} onRetry={() => void load()} />;
  if (!d || !form || !sd) return <Skeleton rows={7} cols={4} />;
  const paperOptions = Array.from(new Map(d.thanh_vien.filter((x) => x.giay_id != null).map((x) => [x.giay_id!, x.giay_ten])));
  const totalMaterials = materials?.items.length ?? 0;
  const commonStepLabor = sd.gop.reduce((sum, g) => sum + (g.khoan_tien ?? 0), 0);

  return (
    <div className="khsx-detail bg2-detail">
      <header className="khsx-detail__hero bg2-detail__hero">
        <button type="button" className="khsx-back" onClick={onBack}>‹ Quay lại danh sách</button>
        <div className="bg2-detail__title-row">
          <div><p className="eyebrow">Sản xuất · Bài ghép 2</p><div className="bg2-detail__identity"><h1 className="khsx-detail__ma">{d.ma}</h1><TrangThaiPill tt={d.trang_thai} lg />{d.is_rush && <ChipGap />}</div><p className="bg2-detail__name">{d.ten || `Bài ghép ${d.ma}`}</p></div>
          <div className="bg2-detail__actions">
            {canDelete && <Button variant="ghost" onClick={() => setConfirmDelete(true)}><Icon name="trash" size={14} /> Xóa</Button>}
            {d.trang_thai === "san_sang" ? canUpdate ? <Button variant="secondary" onClick={() => token && mutate(() => api.baiGhep2.setTrangThai(token, id, "nhap"))}>Mở lại để sửa</Button> : null
              : <Button variant="accent" disabled={!canUpdate || d.thieu.length > 0} onClick={() => token && mutate(() => api.baiGhep2.setTrangThai(token, id, "san_sang"))}>Sẵn sàng xếp lịch</Button>}
          </div>
        </div>
      </header>

      <section className="bg2-kpi" aria-label="Tóm tắt bài ghép">
        <Kpi label="Số lệnh" value={num(d.thanh_vien.length)} />
        <Kpi label="Tờ chạy" value={num(d.so_to.so_to_tot)} />
        <Kpi label="Giấy lĩnh kho" value={num(d.so_to.to_nguyen_can)} />
        <Kpi label="Bước chung" value={num(d.so_to.so_buoc_chung)} />
        <Kpi label="Vật tư" value={materials ? num(totalMaterials) : "Xem tab"} />
        <Kpi label="Hạn" value={ngay(d.han_hoan_thanh_sx)} danger={classHan(d.han_hoan_thanh_sx)} />
        {commonStepLabor > 0 && <Kpi label="Khoán bước chung" value={`${num(commonStepLabor)} đ`} accent />}
      </section>

      {d.thieu.length > 0 && <div className="bg2-status-line" role="status"><strong>Còn thiếu:</strong> {d.thieu.map((x) => BAI_GHEP_THIEU_LABELS[x] ?? x).join(" · ")}</div>}
      {d.canh_bao.length > 0 && <div className="bg2-status-line bg2-status-line--warn"><strong>Lưu ý:</strong> {d.canh_bao.map((x) => BAI_GHEP_CANH_BAO_LABELS[x] ?? x).join(" · ")}</div>}
      {err && <BangLoi text={err} onRetry={() => void load()} />}
      {stale && <div className="bg2-status-line bg2-status-line--warn" role="status">
        Dữ liệu trên máy chủ vừa thay đổi. Bản đang nhập vẫn được giữ. {" "}
        <button type="button" className="khsx-xlink" onClick={() => { setStale(false); void load(); }}>Nạp lại</button>
      </div>}

      <div className="khsx-tabs bg2-tabs" role="tablist" aria-label="Nội dung bài ghép"
        onKeyDown={(event) => {
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          const current = BAI_GHEP_2_TABS.findIndex((item) => item.key === tab);
          const next = event.key === "Home" ? 0 : event.key === "End" ? BAI_GHEP_2_TABS.length - 1
            : (current + (event.key === "ArrowRight" ? 1 : -1) + BAI_GHEP_2_TABS.length) % BAI_GHEP_2_TABS.length;
          setTab(BAI_GHEP_2_TABS[next].key);
          requestAnimationFrame(() => document.getElementById(`bg2-tab-${BAI_GHEP_2_TABS[next].key}`)?.focus());
        }}>
        {BAI_GHEP_2_TABS.map((item) => <button key={item.key} type="button" role="tab"
          id={`bg2-tab-${item.key}`} aria-selected={tab === item.key} aria-controls={`bg2-panel-${item.key}`}
          tabIndex={tab === item.key ? 0 : -1}
          className={`khsx-tabs__btn ${tab === item.key ? "is-active" : ""}`} onClick={() => setTab(item.key)}>
          {item.label}{dirty && (item.key === "chung" || item.key === "quycach") && <span className="khsx-tabs__dot" aria-label="có thay đổi chưa lưu" />}
        </button>)}
      </div>

      {tab === "chung" && <section className="khsx-panel bg2-panel" role="tabpanel" id="bg2-panel-chung" aria-labelledby="bg2-tab-chung">
        <PanelHead icon="pencil" title="Thông tin kế hoạch" action={dirty ? <><Button variant="ghost" onClick={() => setForm(toForm(d))}>Hoàn tác</Button><Button variant="primary" loading={saving} onClick={save}>Lưu</Button></> : null} />
        <div className="bg2-form-grid">
          <label className="khsx-field"><span>Tên bài ghép</span><input disabled={!canUpdate} value={form.ten} onChange={(e) => setForm({ ...form, ten: e.target.value })} /></label>
          <label className="khsx-field"><span>Hạn hoàn thành sản xuất</span><input type="date" disabled={!canUpdate} value={form.han_hoan_thanh_sx ?? ""} onChange={(e) => setForm({ ...form, han_hoan_thanh_sx: e.target.value || null })} /></label>
          <label className="khsx-field"><span>Người phụ trách</span><select disabled={!canUpdate} value={form.nguoi_phu_trach_id ?? ""} onChange={(e) => setForm({ ...form, nguoi_phu_trach_id: e.target.value ? Number(e.target.value) : null })}><option value="">— chưa phân công —</option>{form.nguoi_phu_trach_id != null && !owners.some((x) => x.id === form.nguoi_phu_trach_id) && <option value={form.nguoi_phu_trach_id}>{d.nguoi_phu_trach_ten || `Người dùng #${form.nguoi_phu_trach_id}`}</option>}{owners.map((owner) => <option key={owner.id} value={owner.id}>{owner.ten}</option>)}</select></label>
          <label className="bg2-check"><input type="checkbox" disabled={!canUpdate} checked={form.is_rush} onChange={(e) => setForm({ ...form, is_rush: e.target.checked })} /><span>Hàng gấp · ưu tiên ở xưởng</span></label>
          <label className="khsx-field bg2-form-wide"><span>Ghi chú kế hoạch</span><textarea rows={3} disabled={!canUpdate} value={form.ghi_chu ?? ""} onChange={(e) => setForm({ ...form, ghi_chu: e.target.value })} /></label>
        </div>
        <div className="bg2-members-head"><h3>Thành viên ({d.thanh_vien.length})</h3>{canUpdate && <Button variant="secondary" onClick={() => setMemberPicker(true)}><Icon name="plus" size={14} /> Thêm lệnh</Button>}</div>
        <div className="bg2-members">{d.thanh_vien.map((tv) => <div className="bg2-member" key={tv.thanh_vien_id}>
          <button type="button" className="bg2-member__main" onClick={() => navigate?.("ke-hoach-sx", { openLsxId: tv.lsx_id })}><strong>{tv.lsx_ma}</strong><span>{tv.lsx_ten || "—"}</span></button>
          <span>{num(tv.so_luong_dat)} {tv.don_vi_tinh}</span><span>{tv.so_con_tren_to} con/tờ</span>
          {canUpdate && <button type="button" className="bg2-icon-btn" title="Bỏ lệnh khỏi bài" aria-label={`Bỏ ${tv.lsx_ma}`} onClick={() => token && mutate(() => api.baiGhep2.boThanhVien(token, id, tv.thanh_vien_id))}><Icon name="x" size={15} /></button>}
        </div>)}</div>
      </section>}

      {tab === "quycach" && <section className="khsx-panel bg2-panel" role="tabpanel" id="bg2-panel-quycach" aria-labelledby="bg2-tab-quycach">
        <PanelHead icon="settings" title="Quy cách tờ ghép" action={dirty ? <Button variant="primary" loading={saving} onClick={save}>Lưu quy cách</Button> : null} />
        <div className="bg2-form-grid bg2-form-grid--spec">
          <label className="khsx-field"><span>Giấy chạy chung</span><select disabled={!canUpdate} value={form.giay_id ?? ""} onChange={(e) => setForm({ ...form, giay_id: e.target.value ? Number(e.target.value) : null })}><option value="">— chọn giấy —</option>{paperOptions.map(([paperId, name]) => <option key={paperId} value={paperId}>{name || `Giấy #${paperId}`}</option>)}</select></label>
          <label className="khsx-field"><span>Khổ dài (mm)</span><input type="number" min={0} disabled={!canUpdate} value={form.kho_in_dai ?? ""} onChange={(e) => setForm({ ...form, kho_in_dai: e.target.value ? Number(e.target.value) : null })} /></label>
          <label className="khsx-field"><span>Khổ rộng (mm)</span><input type="number" min={0} disabled={!canUpdate} value={form.kho_in_rong ?? ""} onChange={(e) => setForm({ ...form, kho_in_rong: e.target.value ? Number(e.target.value) : null })} /></label>
          <label className="khsx-field"><span>Hao setup</span><input type="number" min={0} disabled={!canUpdate} value={form.hao_hut_setup ?? ""} onChange={(e) => setForm({ ...form, hao_hut_setup: e.target.value ? Number(e.target.value) : null })} /></label>
          <label className="khsx-field"><span>Hao chạy</span><input type="number" min={0} disabled={!canUpdate} value={form.hao_hut_chay ?? ""} onChange={(e) => setForm({ ...form, hao_hut_chay: e.target.value ? Number(e.target.value) : null })} /></label>
        </div>
        <div className="bg2-spec-list">{d.thanh_vien.map((tv) => <div className="bg2-spec-row" key={tv.thanh_vien_id}>
          <div><strong>{tv.lsx_ma}</strong><span>{tv.giay_ten || "Chưa có giấy"} · {tv.kho_tp || "chưa có khổ TP"} · {tv.so_mau_a ?? 0}/{tv.so_mau_b ?? 0}</span></div>
          <ConInput value={tv.so_con_tren_to} disabled={!canUpdate}
            onSave={(value) => token ? mutate(() => api.baiGhep2.suaThanhVien(token, id, tv.thanh_vien_id, value)) : Promise.resolve(false)} />
          <div className="bg2-spec-row__numbers"><span>Cần <b>{num(tv.nhu_cau_to)} tờ</b></span><span>Dư <b>{num(tv.du_to)} tờ</b></span></div>
        </div>)}</div>
      </section>}

      {tab === "routing" && <section className="khsx-panel bg2-panel bg2-panel--routing" role="tabpanel" id="bg2-panel-routing" aria-labelledby="bg2-tab-routing">
        <PanelHead icon="workflow" title={`Công đoạn sản xuất · ${sd.gop.length} bước chung`} />
        <BaiGhepDagCanvas sd={sd} chon={drawer?.step_key ?? null} canUpdate={canUpdate}
          onChon={(value) => typeof value === "string" && setDrawer(sd.gop.find((g) => g.step_key === value) ?? null)}
          onMoLenh={(lsxId) => navigate?.("ke-hoach-sx", { openLsxId: lsxId })}
          onGop={group}
          onTach={(key) => token ? mutate(() => api.baiGhep2.tach(token, id, key)) : Promise.resolve()}
          onHoiUngVien={(keys) => token ? api.baiGhep2.ungVienGop(token, id, keys).then((x) => x.ung_vien) : Promise.resolve({})}
          onMoBuocChung={(key) => setDrawer(sd.gop.find((g) => g.step_key === key) ?? null)}
          onSuaCon={(tvId, con) => token ? mutate(() => api.baiGhep2.suaThanhVien(token, id, tvId, con)) : Promise.resolve()} />
      </section>}

      {tab === "vattu" && <section className="khsx-panel bg2-panel" role="tabpanel" id="bg2-panel-vattu" aria-labelledby="bg2-tab-vattu">
        <PanelHead icon="box" title="Vật tư hiệu lực" />
        {materials == null ? <Skeleton rows={4} cols={3} /> : materials.items.length === 0 ? <EmptyState icon="box" title="Chưa có nhu cầu vật tư" sub="Vật tư của bước chung và bước riêng sẽ xuất hiện tại đây." />
          : <div className="bg2-materials">{materials.items.map((group) => <section key={`${group.hang_loai}:${group.hang_id}`} className="bg2-material">
            <div className="bg2-material__head"><div><strong>{group.hang_ma ? `${group.hang_ma} · ` : ""}{group.hang_ten || "Vật tư"}</strong><span>{group.loai_nhom}</span></div><b>{num(group.tong_can)} {group.don_vi_goc}</b></div>
            {group.dong.map((row, index) => <div className="bg2-material__row" key={`${row.ma}:${index}`}><span className={`bg2-scope bg2-scope--${row.pham_vi}`}>{row.pham_vi === "bai_ghep" ? "Bước chung" : row.ma}</span><span>{row.ten_viec || row.ma}</span><strong>{row.nhu_cau_hien_thi || num(row.nhu_cau)}</strong>{row.pham_vi === "bai_ghep" && row.gang_step_key && canUpdate ? <button type="button" className="bg2-icon-btn" title="Sửa vật tư bước chung" onClick={() => setDrawer(sd.gop.find((g) => g.step_key === row.gang_step_key) ?? null)}><Icon name="pencil" size={14} /></button> : <span />}</div>)}
          </section>)}</div>}
        {materials?.bo_qua.length ? <div className="bg2-status-line bg2-status-line--warn">{materials.bo_qua.map((x) => `${x.ma}: ${x.ly_do}`).join(" · ")}</div> : null}
      </section>}

      {tab === "nhatky" && <section className="khsx-panel bg2-panel" role="tabpanel" id="bg2-panel-nhatky" aria-labelledby="bg2-tab-nhatky">
        <PanelHead icon="clock" title="Nhật ký hoạt động" />
        {activity == null ? <Skeleton rows={5} cols={2} /> : activity.length === 0 ? <EmptyState icon="clock" title="Chưa có hoạt động" /> : <ol className="bg2-activity">{activity.map((item, index) => <li key={`${item.at}:${index}`}><span className="bg2-activity__dot" /><div><strong>{item.action}</strong><p>{item.actor || "Hệ thống"} · {ngayGio(item.at)}</p>{item.detail && <p>{item.detail}</p>}</div></li>)}</ol>}
      </section>}

      {drawer && <div className="bg2-drawer-scrim" onMouseDown={() => setDrawer(null)}><aside ref={dialogRef} className="bg2-drawer" role="dialog" aria-modal="true" aria-label={`Khai lại bước chung ${drawer.ten}`} onMouseDown={(e) => e.stopPropagation()}>
        <header className="bg2-drawer__head"><div><span>Bước chung</span><h2>{drawer.ten}</h2><p>{drawer.thanh_vien.length} lệnh · số lượng, hao và thời lượng do hệ thống tính</p></div><button type="button" className="bg2-icon-btn" aria-label="Đóng" autoFocus onClick={() => setDrawer(null)}><Icon name="x" size={18} /></button></header>
        {!drawer.da_lap_ke_hoach && <div className="bg2-status-line">Bước vừa gộp chưa có cấu hình kế hoạch. Hãy khai lại tổ, máy, đầu việc và vật tư.</div>}
        {err && <div className="banner banner--error" role="alert">{err}</div>}
        <div className="bg2-drawer__body"><BuocChungForm g={drawer} canUpdate={canUpdate}
          onLuu={async (body: BaiGhepBuocChungBody) => {
            if (!token) return false;
            const saved = await mutate(() => api.baiGhep2.luuBuocChung(token, id, drawer.step_key, body));
            if (saved) setDrawer(null);
            return saved;
          }}
          onTach={async () => { if (!token) return; if (await mutate(() => api.baiGhep2.tach(token, id, drawer.step_key))) setDrawer(null); }} /></div>
      </aside></div>}

      {memberPicker && <MemberPicker dialogRef={dialogRef} exclude={new Set(d.thanh_vien.map((x) => x.lsx_id))} onClose={() => setMemberPicker(false)} onAdd={async (ids) => { if (!token) return; if (await mutate(() => api.baiGhep2.themThanhVien(token, id, ids))) setMemberPicker(false); }} />}
      <ConfirmDialog open={confirmDelete} title="Xóa bài ghép 2?" message="Các routing LSX gốc vẫn được giữ nguyên. Lớp bước chung của bài sẽ bị xóa." danger busy={saving} confirmLabel="Xóa bài ghép" onCancel={() => setConfirmDelete(false)} onConfirm={async () => { if (!token) return; setSaving(true); try { await api.baiGhep2.remove(token, id); onChanged(); onBack(); } catch (e) { setErr(loi(e)); setConfirmDelete(false); } finally { setSaving(false); } }} />
    </div>
  );
}

function Kpi({ label, value, danger, accent }: { label: string; value: string; danger?: string; accent?: boolean }) {
  return <div className={`khsx-kpi-tile ${accent ? "khsx-kpi-tile--rust" : ""}`}><span className="khsx-kpi-tile__label">{label}</span><span className={`khsx-kpi-tile__val ${danger ?? ""}`}>{value || "—"}</span></div>;
}

export function ConInput({ value, disabled, onSave }: { value: number; disabled: boolean; onSave: (value: number) => Promise<unknown> }) {
  const [draft, setDraft] = useState(String(value));
  const [busy, setBusy] = useState(false);
  useEffect(() => setDraft(String(value)), [value]);
  const commit = async () => {
    const next = Math.max(0, Number(draft) || 0);
    setDraft(String(next));
    if (next === value) return;
    setBusy(true);
    try { await onSave(next); } finally { setBusy(false); }
  };
  return <label><span>Con trên tờ</span><input type="number" min={0} disabled={disabled || busy} value={draft}
    onChange={(e) => setDraft(e.target.value)} onBlur={() => void commit()}
    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); e.currentTarget.blur(); } }} /></label>;
}

function PanelHead({ icon, title, action }: { icon: "pencil" | "settings" | "workflow" | "box" | "clock"; title: string; action?: React.ReactNode }) {
  return <div className="bg2-panel__head"><div><Icon name={icon} size={16} /><h2>{title}</h2></div>{action && <div className="bg2-panel__actions">{action}</div>}</div>;
}

function MemberPicker({ dialogRef, exclude, onClose, onAdd }: { dialogRef: React.RefObject<HTMLElement>; exclude: ReadonlySet<number>; onClose: () => void; onAdd: (ids: number[]) => Promise<void> }) {
  const { token } = useAuth();
  const [rows, setRows] = useState<HangChoGhepItem[] | null>(null);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (token) api.baiGhep2.hangCho(token).then((r) => setRows(r.items.filter((x) => !exclude.has(x.lsx_id)))); }, [exclude, token]);
  return <div className="bg2-drawer-scrim" onMouseDown={onClose}><aside ref={dialogRef} className="bg2-drawer bg2-drawer--picker" role="dialog" aria-modal="true" aria-label="Thêm lệnh vào bài" onMouseDown={(e) => e.stopPropagation()}>
    <header className="bg2-drawer__head"><div><span>Thành viên</span><h2>Thêm lệnh vào bài</h2></div><button type="button" className="bg2-icon-btn" aria-label="Đóng" autoFocus onClick={onClose}><Icon name="x" size={18} /></button></header>
    <div className="bg2-drawer__body bg2-picker">{rows == null ? <Skeleton rows={5} cols={2} /> : rows.length === 0 ? <EmptyState icon="layers" title="Không còn lệnh phù hợp" /> : rows.map((row) => <label key={row.lsx_id} className="bg2-picker__row"><input type="checkbox" checked={picked.has(row.lsx_id)} onChange={() => setPicked((old) => { const next = new Set(old); next.has(row.lsx_id) ? next.delete(row.lsx_id) : next.add(row.lsx_id); return next; })} /><span><strong>{row.ma}</strong><small>{row.ten}</small></span></label>)}</div>
    <footer className="bg2-drawer__foot"><Button variant="ghost" onClick={onClose}>Hủy</Button><Button variant="accent" disabled={!picked.size || busy} loading={busy} onClick={async () => { setBusy(true); try { await onAdd([...picked]); } finally { setBusy(false); } }}>Thêm {picked.size || ""} lệnh</Button></footer>
  </aside></div>;
}
