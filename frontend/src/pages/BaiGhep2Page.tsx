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
import { BaiGhepDagCanvas, mauNhanh } from "../components/BaiGhepDagCanvas";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Icon } from "../components/Icons";
import { MucInHang } from "../components/MucIn";
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
  // KHÔNG mang `hao_hut_setup/chay` vào form: hao là HỆ QUẢ của bù hao từng bước chung, gõ đè chỉ
  // để hai con số lệch nhau. Cột vẫn còn ở DB (bài cũ lỡ khai tay vẫn được tôn trọng) và PUT dùng
  // `exclude_unset` nên vắng mặt ở đây = giữ nguyên, không phải xoá về null.
});

/** Nhãn cách in — cùng bộ chữ với màn Lệnh sản xuất, đừng đẻ bộ thứ hai. */
const CACH_IN_NHAN: Record<string, string> = {
  mot_mat: "1 mặt", hai_mat: "2 mặt (AB)", tu_tro: "Tự trở", tro_nhip: "Trở nhíp",
};

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
    // Drawer bước chung mở đầu bằng thanh tab (không còn nút Đóng autoFocus), nên tự đưa focus vào
    // khung — không thì bẫy Tab ở effect trên không có phần tử nào để giữ.
    if (drawer) dialogRef.current?.focus();
  }, [drawer]);
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
  // Khổ tờ mua về. `0 × 0` là giấy cuộn / chưa khai khổ — hiện gạch ngang, đừng bày số 0 rồi để
  // người ta tưởng đã khai.
  const khoNguyen = d.kho_nguyen_dai && d.kho_nguyen_rong
    ? `${num(d.kho_nguyen_dai)} × ${num(d.kho_nguyen_rong)} mm` : "—";
  // Chỉ số màu do SERVER gán cho từng nhánh trong sơ đồ. Lấy lại đúng nó (không đánh số theo thứ
  // tự thành viên) để một lệnh giữ nguyên màu ở cả tab Quy cách lẫn tab Công đoạn.
  const mauTheoLsx = new Map(sd.nhanh.map((n) => [n.lsx_id, n.mau]));
  const mauCua = (lsxId: number) => mauTheoLsx.get(lsxId) ?? 0;
  const totalMaterials = materials?.items.length ?? 0;
  // `drawer` là ẢNH CHỤP lúc bấm mở. Sau khi lưu, `sd` được nạp lại nên phải bám theo `step_key` để
  // drawer hiện số MỚI (rơi về ảnh cũ nếu bước vừa bị tách khỏi bài).
  const buocMo = drawer ? (sd.gop.find((g) => g.step_key === drawer.step_key) ?? drawer) : null;
  const viTriBuoc = buocMo ? sd.gop.findIndex((g) => g.step_key === buocMo.step_key) : -1;
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

      {tab === "quycach" && <section className="khsx-panel bg2-panel bg2-panel--spec" role="tabpanel" id="bg2-panel-quycach" aria-labelledby="bg2-tab-quycach">
        <PanelHead icon="settings" title="Quy cách tờ ghép" action={dirty ? <><Button variant="ghost" onClick={() => setForm(toForm(d))}>Hoàn tác</Button><Button variant="primary" loading={saving} onClick={save}>Lưu quy cách</Button></> : null} />

        <div className="khsx-spec__card">
          <div className="khsx-spec__card-head">
            <div className="khsx-spec__card-icon"><Icon name="printer" size={16} /></div>
            <h4 className="khsx-spec__title">Giấy &amp; tờ ghép</h4>
            <span className="khsx-spec__hint">thông số — sửa được</span>
          </div>
          <div className="khsx-spec__card-body">
            <div className="khsx-kvgrid">
              <label className={`khsx-kv ${canUpdate ? "khsx-kv--edit" : ""}`}>
                <span className="khsx-kv__key">Giấy chạy chung</span>
                <select className="khsx-kv__input" disabled={!canUpdate} value={form.giay_id ?? ""}
                  onChange={(e) => setForm({ ...form, giay_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">— chọn giấy —</option>
                  {paperOptions.map(([paperId, name]) => <option key={paperId} value={paperId}>{name || `Giấy #${paperId}`}</option>)}
                </select>
              </label>
              {/* Định lượng + khổ tờ mua về ĐỌC THẲNG danh mục giấy, bài không giữ bản sao. Giữ
                  bản sao là chỗ để hai bên lệch nhau, mà khi lệch thì không ai biết kho phải xuất
                  theo con số nào. Đổi giấy rồi Lưu là hai ô này đổi theo. */}
              <KV k="Định lượng" v={d.gsm ? `${num(d.gsm)} gsm` : "—"} mono />
              <KV k="Khổ giấy nguyên" v={khoNguyen} mono />
              <KVNum k="Khổ tờ ghép dài" suffix="mm" disabled={!canUpdate}
                v={form.kho_in_dai ?? undefined} onChange={(x) => setForm({ ...form, kho_in_dai: x || null })} />
              <KVNum k="Khổ tờ ghép rộng" suffix="mm" disabled={!canUpdate}
                v={form.kho_in_rong ?? undefined} onChange={(x) => setForm({ ...form, kho_in_rong: x || null })} />
              <KV k="Cách in" v={CACH_IN_NHAN[d.quy_cach_in ?? ""] ?? "—"} badge />
              {/* Mực của BÀI là HỢP tập mực mọi lệnh — chung tờ là chung MỘT bộ bản. Nên đây là số
                  ĐỌC: muốn sửa thì sửa ở lệnh, không mở lối khai mực lần thứ hai. Dùng lại đúng
                  khối chip của phiếu/lệnh để ba màn nói cùng một số kẽm. */}
              <div className="khsx-kv khsx-kv--span">
                <span className="khsx-kv__key">Mực in cả bài</span>
                <MucInHang mucA={d.muc_a} mucB={d.muc_b} quyCachIn={d.quy_cach_in ?? "mot_mat"}
                  disabled onChange={() => {}} />
              </div>
            </div>
            {d.quy_cach_in_lech && <p className="khsx-spec__canhbao">
              Các lệnh khai cách in KHÁC nhau — số kẽm bên dưới đếm theo “{CACH_IN_NHAN[d.quy_cach_in ?? ""] ?? "—"}”.
            </p>}
          </div>
        </div>

        <div className="khsx-spec__card">
          <div className="khsx-spec__card-head">
            <div className="khsx-spec__card-icon"><Icon name="grid" size={16} /></div>
            <h4 className="khsx-spec__title">Máy tự tính</h4>
            <span className="khsx-spec__hint">hệ quả của thông số trên — chỉ đọc</span>
          </div>
          <div className="khsx-spec__card-body">
            <div className="khsx-kvgrid">
              <KV k="Tờ chạy" v={`${num(d.so_to.so_to_tot)} tờ`} mono />
              <KV k="Hao setup" v={`${num(d.so_to.hao_setup_de_xuat)} tờ`} mono />
              <KV k="Hao chạy" v={`${num(d.so_to.hao_chay_de_xuat)} tờ`} mono />
              <KV k="Tỷ lệ hao" v={`${d.so_to.ty_le_hao}%`} mono />
              <KV k="Giấy lĩnh kho" v={`${num(d.so_to.to_nguyen_can)} tờ`} mono />
              <KV k="Số kẽm" v={d.so_kem ? num(d.so_kem) : "—"} mono />
              <KV k="Số màu" v={`${d.so_mau_a}/${d.so_mau_b}${d.so_mau_pha ? ` · ${d.so_mau_pha} pha` : ""}`} mono />
              <KV k="Lấp đầy tờ" v={d.so_to.fill_pct != null ? `${d.so_to.fill_pct}%` : "—"} mono />
              <KV k="Bước chạy chung" v={num(d.so_to.so_buoc_chung)} mono />
            </div>
            {d.so_to.hao_theo_buoc.length > 0 && <p className="khsx-nhom__sub">
              Hao theo bước: {d.so_to.hao_theo_buoc.map((x) => `${x.ten} ${num(x.hao)} tờ`).join(" · ")}
            </p>}
            {/* Bài khai tay TỪ TRƯỚC vẫn đang đè số máy tính. Ô nhập đã gỡ, không có lối quay lại
                thì nó kẹt vĩnh viễn ở con số cũ — một nút trả về, không dựng lại ô. */}
            {(d.hao_hut_setup != null || d.hao_hut_chay != null) && <div className="bg2-status-line bg2-status-line--warn">
              <strong>Hao đang khai tay:</strong> {num((d.hao_hut_setup ?? 0) + (d.hao_hut_chay ?? 0))} tờ,
              đang đè số máy tính ({num(d.so_to.hao_de_xuat)} tờ).{" "}
              {canUpdate && <button type="button" className="khsx-xlink"
                onClick={() => token && mutate(() => api.baiGhep2.update(token, id, { hao_hut_setup: null, hao_hut_chay: null }))}>
                Dùng số máy tính
              </button>}
            </div>}
          </div>
        </div>

        <div className="khsx-spec__card">
          <div className="khsx-spec__card-head">
            <div className="khsx-spec__card-icon"><Icon name="layers" size={16} /></div>
            <h4 className="khsx-spec__title">Các lệnh trên tờ · {d.thanh_vien.length}</h4>
            <span className="khsx-spec__hint">con/tờ — sửa được</span>
          </div>
          <div className="khsx-spec__card-body">
            {/* Tờ dùng CHUNG nên không có "tờ của lệnh nào"; chia được là phần giấy mỗi lệnh gánh
                theo diện tích chiếm trên tờ. Dải này vẽ đúng `ty_le_giay` server trả, không phải
                ước lượng cho đẹp — màu lấy chung nguồn với sơ đồ để nhìn tab nào cũng ra một lệnh. */}
            <div className="bg2-share" role="img"
              aria-label={`Phần giấy mỗi lệnh gánh: ${d.thanh_vien.map((tv) => `${tv.lsx_ma} ${tv.ty_le_giay}%`).join(", ")}`}>
              {d.thanh_vien.map((tv) => <span key={tv.thanh_vien_id} className="bg2-share__seg"
                style={{ flexGrow: Math.max(tv.ty_le_giay, 1), background: mauNhanh(mauCua(tv.lsx_id)) }}
                title={`${tv.lsx_ma} · ${tv.ty_le_giay}% giấy · ${num(tv.phan_giay_to)} tờ`}>
                <b>{tv.ty_le_giay}%</b>
              </span>)}
            </div>
            <div className="bg2-spec-list">{d.thanh_vien.map((tv) => <div className="bg2-spec-row" key={tv.thanh_vien_id}>
              <div className="bg2-spec-row__id">
                <span className="bg2-spec-row__dot" style={{ background: mauNhanh(mauCua(tv.lsx_id)) }} aria-hidden="true" />
                <div>
                  <strong>{tv.lsx_ma}</strong>
                  <span>{tv.lsx_ten || "—"}</span>
                  <span>{tv.giay_ten || "Chưa có giấy"} · khổ TP {tv.kho_tp || "—"} · {tv.so_mau_a ?? 0}/{tv.so_mau_b ?? 0}
                    {[...tv.muc_a, ...tv.muc_b].length > 0 && ` (${[...new Set([...tv.muc_a, ...tv.muc_b])].join("+")})`}</span>
                </div>
              </div>
              <div className="bg2-spec-row__con">
                <ConInput value={tv.so_con_tren_to} disabled={!canUpdate}
                  onSave={(value) => token ? mutate(() => api.baiGhep2.suaThanhVien(token, id, tv.thanh_vien_id, value)) : Promise.resolve(false)} />
                {/* Gợi ý là số SERVER tính (tối đa theo khổ · cân sản lượng để bớt dư). Bấm mới
                    ghi — máy không tự sửa con/tờ của người bình bài. */}
                <span className="bg2-spec-row__hint">
                  {tv.con_toi_da > 0 && `tối đa ${tv.con_toi_da}`}
                  {canUpdate && tv.con_goi_y > 0 && tv.con_goi_y !== tv.so_con_tren_to && <>
                    {tv.con_toi_da > 0 && " · "}
                    <button type="button" className="khsx-xlink"
                      onClick={() => token && mutate(() => api.baiGhep2.suaThanhVien(token, id, tv.thanh_vien_id, tv.con_goi_y))}>
                      gợi ý {tv.con_goi_y}
                    </button>
                  </>}
                </span>
              </div>
              <div className="bg2-spec-row__numbers">
                <span>Chiếm <b>{tv.ty_le_giay}%</b> giấy · {num(tv.phan_giay_to)} tờ</span>
                <span>Cần <b>{num(tv.nhu_cau_to)} tờ</b></span>
                <span>Dư <b>{num(tv.du_to)} tờ</b></span>
                <span>Ra <b>{num(tv.san_luong_du_kien)}</b> / {num(tv.so_luong_dat)} {tv.don_vi_tinh || ""}</span>
              </div>
            </div>)}</div>
          </div>
        </div>
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

      {buocMo && <div className="khsx-scrim" onMouseDown={(e) => e.target === e.currentTarget && setDrawer(null)}>
        <aside ref={dialogRef} tabIndex={-1} className={`khsx-drawer khsx-drawer--buoc khsx-drawer--${buocMo.loai_buoc}`}
          role="dialog" aria-modal="true" aria-label={`Khai lại bước chung ${buocMo.ten}`}>
          <BuocChungForm g={buocMo} canUpdate={canUpdate}
            index={viTriBuoc} tong={sd.gop.length}
            onPrev={viTriBuoc > 0 ? () => setDrawer(sd.gop[viTriBuoc - 1]) : undefined}
            onNext={viTriBuoc >= 0 && viTriBuoc < sd.gop.length - 1 ? () => setDrawer(sd.gop[viTriBuoc + 1]) : undefined}
            onClose={() => setDrawer(null)}
            banner={<>
              {!buocMo.da_lap_ke_hoach && <div className="bg2-status-line">Bước vừa gộp chưa có cấu hình kế hoạch. Hãy khai lại tổ, máy, đầu việc và vật tư.</div>}
              {err && <div className="banner banner--error" role="alert">{err}</div>}
            </>}
            onLuu={async (body: BaiGhepBuocChungBody) => {
              if (!token) return false;
              // Lưu xong GIỮ drawer mở (bản cũ đóng luôn): drawer nay có 5-6 tab, đá người dùng ra
              // ngoài sau mỗi lần lưu thì họ phải mở lại để khai tiếp tab kế. `mutate` nạp lại sơ đồ
              // và `buocMo` bám theo `step_key` nên số trong drawer là số server vừa tính lại.
              return await mutate(() => api.baiGhep2.luuBuocChung(token, id, buocMo.step_key, body));
            }}
            onTach={async () => { if (!token) return; if (await mutate(() => api.baiGhep2.tach(token, id, buocMo.step_key))) setDrawer(null); }} />
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

/** Một ô key-value CHỈ ĐỌC. Cùng bộ class với tab Quy cách của lệnh sản xuất — hai màn nói cùng
 *  một thứ thì phải nhìn giống nhau, không đẻ kiểu trình bày thứ hai. */
function KV({ k, v, mono = false, badge = false }: { k: string; v: React.ReactNode; mono?: boolean; badge?: boolean }) {
  const rong = typeof v === "string" && (v === "—" || v === "");
  return <div className="khsx-kv">
    <span className="khsx-kv__key">{k}</span>
    <span className={`khsx-kv__val ${mono ? "khsx-num" : ""} ${rong ? "is-nil" : ""} ${badge && !rong ? "is-badge" : ""}`}>{v}</span>
  </div>;
}

/** Ô số SỬA ĐƯỢC trong cùng lưới. `undefined` hiện rỗng chứ không hiện 0 — chưa khai khác 0. */
function KVNum({ k, v, onChange, disabled, suffix }: {
  k: string; v: number | undefined; onChange: (n: number) => void; disabled?: boolean; suffix?: string;
}) {
  return <label className={`khsx-kv ${disabled ? "" : "khsx-kv--edit"}`}>
    <span className="khsx-kv__key">{k}{suffix ? ` (${suffix})` : ""}</span>
    <input className="khsx-kv__input" type="number" min={0} disabled={disabled} value={v ?? ""}
      onChange={(e) => onChange(Math.max(0, Number(e.target.value) || 0))} />
  </label>;
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
