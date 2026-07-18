// THEO DÕI SẢN XUẤT (Chunk C · §13.3–13.4) — góc nhìn CHỦ XƯỞNG / TỔ TRƯỞNG, KHÔNG phải màn thợ.
//
// Luồng 3 tầng (bám ảnh chủ gửi + §13.4):
//   1) CÂY TỔ  — phòng/tổ khối Sản xuất dạng cây, mỗi tổ đếm việc (ĐẾN LƯỢT = cần thao tác ngay /
//      đang chạy). Bấm 1 tổ →
//   2) LỆNH CỦA TỔ — các lệnh đã phát có công đoạn thuộc tổ; đến-lượt lên đầu. Bấm 1 lệnh →
//   3) MÀN THỰC THI — nguyên lệnh + routing dạng THẺ (chờ/đang/xong). Chỉ thẻ công đoạn của TỔ MÌNH
//      và ĐÚNG bước đến lượt mới thao tác (Bắt đầu → Hoàn thành, ẩn dụ quét QR); bước khác chỉ xem.
//
// REAL-TIME (§13.5): tổ A hoàn thành → hub đẩy 'lenh_sx_routing' (kèm tổ ĐẾN LƯỢT kế) → màn này
// refetch + "ting" đúng tổ đang xem. MÁY CHỈ GHI NHẬN — không phán; backend cổng cứng (chưa tới lượt
// → 409) thì hiện toast đỏ.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  ApiError,
  connectQuoteEvents,
  type Department,
  type LenhSXDetailOut,
  type OrderRow,
  type RoutingStepRow,
  type ToLenh,
  type ToNode,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { ToastStack, useToasts } from "./LsxToast";
import "./lenh-san-xuat.css";

const maLenh = (id: number): string => `LSX-${String(id).padStart(4, "0")}`;
const fmt = (v: number | null | undefined): string =>
  typeof v === "number" ? Math.round(v).toLocaleString("vi-VN") : "—";
const anPhamLabel = (ptpId: number | null): string =>
  ptpId ? `Ấn phẩm #${ptpId}` : "— chưa gắn ấn phẩm";

// Trạng thái 1 bước routing → nhãn + biến thể badge/thẻ (màu app).
const RS_META: Record<string, { label: string; variant: string }> = {
  cho: { label: "Chờ", variant: "wait" },
  dang: { label: "Đang chạy", variant: "run" },
  xong: { label: "Xong", variant: "done" },
};
const rsMeta = (tt: string) => RS_META[tt] ?? { label: tt || "—", variant: "neutral" };

const LENH_META: Record<string, { label: string; variant: string }> = {
  dang_chay: { label: "Đang chạy", variant: "run" },
  xong: { label: "Xong", variant: "done" },
  nhap: { label: "Nháp", variant: "neutral" },
  huy: { label: "Hủy", variant: "danger" },
};
const lenhMeta = (tt: string) => LENH_META[tt] ?? { label: tt || "—", variant: "neutral" };

// ---- Cây tổ: dựng từ parent_id (một nguồn sự thật §13.1) + đếm dồn con lên cha ----
type TreeNode = ToNode & { children: TreeNode[]; depth: number; aggLenh: number; aggDenLuot: number };

function buildTree(nodes: ToNode[]): TreeNode[] {
  const byId = new Map<number, TreeNode>(
    nodes.map((n) => [n.id, { ...n, children: [], depth: 0, aggLenh: 0, aggDenLuot: 0 }]),
  );
  const roots: TreeNode[] = [];
  for (const n of byId.values()) {
    const parent = n.parent_id != null ? byId.get(n.parent_id) : undefined;
    if (parent) parent.children.push(n);
    else roots.push(n);
  }
  const sortRec = (arr: TreeNode[]) => {
    arr.sort((a, b) => a.name.localeCompare(b.name, "vi"));
    arr.forEach((x) => sortRec(x.children));
  };
  sortRec(roots);
  // depth + đếm dồn (cha hiện tổng việc cả nhánh)
  const agg = (n: TreeNode, d: number): [number, number] => {
    n.depth = d;
    let l = n.so_lenh;
    let dl = n.so_den_luot;
    for (const c of n.children) {
      const [cl, cdl] = agg(c, d + 1);
      l += cl;
      dl += cdl;
    }
    n.aggLenh = l;
    n.aggDenLuot = dl;
    return [l, dl];
  };
  roots.forEach((r) => agg(r, 0));
  return roots;
}
function flatten(roots: TreeNode[]): TreeNode[] {
  const out: TreeNode[] = [];
  const walk = (n: TreeNode) => {
    out.push(n);
    n.children.forEach(walk);
  };
  roots.forEach(walk);
  return out;
}

type View =
  | { level: "tree" }
  | { level: "lenh"; to: ToNode }
  | { level: "exec"; to: ToNode; lenhId: number };

export function TheoDoiSanXuatView() {
  const { token } = useAuth();
  const toasts = useToasts();
  const [view, setView] = useState<View>({ level: "tree" });
  const [tick, setTick] = useState(0); // bump → refetch tầng hiện tại (SSE / sau thao tác)

  // Danh mục nền (tải 1 lần): tổ (phòng ban) để resolve tên; đơn để resolve khách/số đơn.
  const [depts, setDepts] = useState<Department[]>([]);
  const [orders, setOrders] = useState<Map<number, OrderRow>>(new Map());
  const deptName = useCallback(
    (id: number | null): string => {
      if (id == null) return "—";
      return depts.find((d) => d.id === id)?.name ?? `Tổ #${id}`;
    },
    [depts],
  );

  useEffect(() => {
    if (!token) return;
    let alive = true;
    (async () => {
      const [dp, od] = await Promise.all([
        api.rbac.departments(token).catch(() => [] as Department[]),
        api.orders.list(token, { size: 200 }).then((r) => r.items).catch(() => [] as OrderRow[]),
      ]);
      if (!alive) return;
      setDepts(dp);
      setOrders(new Map(od.map((o) => [o.id, o])));
    })();
    return () => {
      alive = false;
    };
  }, [token]);

  // Real-time: 1 kết nối SSE cho cả màn; lọc sự kiện sản xuất → refetch + "ting" đúng tổ đang xem.
  const viewRef = useRef(view);
  viewRef.current = view;
  useEffect(() => {
    if (!token) return;
    const close = connectQuoteEvents(token, (e) => {
      if (!e.type.startsWith("lenh_sx")) return;
      setTick((n) => n + 1); // mọi mốc sản xuất → làm tươi số liệu tầng đang mở
      const v = viewRef.current;
      const watchingTo = v.level === "tree" ? null : v.to.id;
      if (e.type === "lenh_sx_routing" && e.pha === "hoan_thanh" && e.to_id != null && e.to_id === watchingTo) {
        toasts.ok("🔔 Đến lượt tổ — sang tổ trước lấy hàng");
      }
    });
    return close;
  }, [token, toasts]);

  if (view.level === "exec") {
    return (
      <ExecView
        to={view.to}
        lenhId={view.lenhId}
        tick={tick}
        orders={orders}
        deptName={deptName}
        toasts={toasts}
        onBack={() => setView({ level: "lenh", to: view.to })}
        afterAction={() => setTick((n) => n + 1)}
      />
    );
  }
  if (view.level === "lenh") {
    return (
      <LenhOfToView
        to={view.to}
        tick={tick}
        orders={orders}
        deptName={deptName}
        toasts={toasts}
        onBack={() => setView({ level: "tree" })}
        onOpen={(lenhId) => setView({ level: "exec", to: view.to, lenhId })}
      />
    );
  }
  return (
    <TreeView
      tick={tick}
      toasts={toasts}
      onPick={(to) => setView({ level: "lenh", to })}
    />
  );
}

// ============================================================ TẦNG 1 — CÂY TỔ
function TreeView({
  tick,
  toasts,
  onPick,
}: {
  tick: number;
  toasts: ReturnType<typeof useToasts>;
  onPick: (to: ToNode) => void;
}) {
  const { token } = useAuth();
  const [nodes, setNodes] = useState<ToNode[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    api.lenhSanXuat
      .toBoard(token)
      .then(setNodes)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được danh sách tổ."));
  }, [token]);
  useEffect(() => {
    load();
  }, [load, tick]);

  const rows = useMemo(() => (nodes ? flatten(buildTree(nodes)) : []), [nodes]);
  const totalDenLuot = useMemo(() => (nodes ?? []).reduce((s, n) => s + n.so_den_luot, 0), [nodes]);

  return (
    <main className="lsx">
      <ToastStack toasts={toasts.toasts} onDismiss={toasts.dismiss} />
      <header className="lsx-head">
        <div className="lsx-head__lead">
          <div className="lsx-eyebrow">
            <span className="sq" /> Sản xuất · Theo dõi
          </div>
          <h1 className="lsx-head__title">Theo dõi sản xuất</h1>
          <p className="lsx-head__sub">
            Các tổ trong khối sản xuất và khối lượng việc theo thời gian thực. Chấm cam =
            <b> đến lượt</b> (cần thao tác ngay), chấm xanh = đang chạy. Bấm một tổ để xem lệnh của tổ.
          </p>
        </div>
        {totalDenLuot > 0 ? (
          <div className="lsx-head__actions">
            <span className="lsx-count lsx-count--hot lsx-count--lg">
              <BellIcon /> {totalDenLuot} việc đến lượt
            </span>
          </div>
        ) : null}
      </header>

      {error ? (
        <div className="banner banner--error" role="alert" style={{ marginTop: "var(--sp-2)" }}>
          <span>{error}</span>
          <button type="button" className="btn btn--ghost" style={{ padding: "4px 12px", fontSize: 12 }} onClick={load}>
            Tải lại
          </button>
        </div>
      ) : null}

      {nodes === null ? (
        <p className="lsx-msg">Đang tải danh sách tổ…</p>
      ) : rows.length === 0 ? (
        <div className="lsx-empty">
          <FactoryIcon />
          <p className="lsx-empty__title">Chưa có tổ sản xuất nào.</p>
          <p className="lsx-empty__sub">
            Đánh dấu <b>“Là bộ phận sản xuất”</b> cho một phòng ở màn Phòng ban — phòng đó và các tổ
            trực thuộc sẽ hiện ở đây.
          </p>
        </div>
      ) : (
        <ul className="lsx-tree">
          {rows.map((n) => {
            const leaf = n.children.length === 0;
            const dl = n.aggDenLuot;
            const live = n.aggLenh;
            const dot = dl > 0 ? "hot" : live > 0 ? "run" : "idle";
            return (
              <li key={n.id} className="lsx-tree__row" style={{ paddingLeft: 8 + n.depth * 24 }}>
                <button
                  type="button"
                  className={`lsx-tree__btn${leaf ? "" : " is-branch"}`}
                  onClick={() => onPick(n)}
                >
                  <span className={`lsx-tree__dot lsx-tree__dot--${dot}`} aria-hidden="true" />
                  <span className="lsx-tree__main">
                    <span className="lsx-tree__name">{n.name}</span>
                    <span className="lsx-tree__code mono">{n.code}</span>
                  </span>
                  <span className="lsx-tree__counts">
                    {dl > 0 ? (
                      <span className="lsx-count lsx-count--hot">
                        <BellIcon /> {dl} đến lượt
                      </span>
                    ) : null}
                    {live > 0 ? (
                      <span className="lsx-count lsx-count--run">{live} đang chạy</span>
                    ) : dl === 0 ? (
                      <span className="lsx-count lsx-count--idle">Rảnh</span>
                    ) : null}
                    <ChevronRightIcon />
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}

// ============================================================ TẦNG 2 — LỆNH CỦA TỔ
function LenhOfToView({
  to,
  tick,
  orders,
  deptName,
  toasts,
  onBack,
  onOpen,
}: {
  to: ToNode;
  tick: number;
  orders: Map<number, OrderRow>;
  deptName: (id: number | null) => string;
  toasts: ReturnType<typeof useToasts>;
  onBack: () => void;
  onOpen: (lenhId: number) => void;
}) {
  const { token } = useAuth();
  const [items, setItems] = useState<ToLenh[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    api.lenhSanXuat
      .lenhOfTo(token, to.id)
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được lệnh của tổ."));
  }, [token, to.id]);
  useEffect(() => {
    load();
  }, [load, tick]);

  return (
    <main className="lsx">
      <ToastStack toasts={toasts.toasts} onDismiss={toasts.dismiss} />
      <button type="button" className="lsx-back" onClick={onBack}>
        <BackIcon /> Cây tổ
      </button>
      <header className="lsx-head">
        <div className="lsx-head__lead">
          <div className="lsx-eyebrow">
            <UsersIcon /> Tổ sản xuất
          </div>
          <h1 className="lsx-head__title">{to.name}</h1>
          <p className="lsx-head__sub">
            Lệnh đã phát có công đoạn thuộc tổ. Thẻ <b>viền cam</b> = đến lượt tổ — bấm để vào thao tác.
          </p>
        </div>
      </header>

      {error ? (
        <div className="banner banner--error" role="alert">
          <span>{error}</span>
          <button type="button" className="btn btn--ghost" style={{ padding: "4px 12px", fontSize: 12 }} onClick={load}>
            Tải lại
          </button>
        </div>
      ) : null}

      {items === null ? (
        <p className="lsx-msg">Đang tải lệnh…</p>
      ) : items.length === 0 ? (
        <div className="lsx-empty">
          <InboxIcon />
          <p className="lsx-empty__title">Tổ chưa có lệnh nào.</p>
          <p className="lsx-empty__sub">
            Lệnh xuất hiện ở đây khi bộ phận kế hoạch <b>phát hành</b> một lệnh có công đoạn thuộc tổ này.
          </p>
        </div>
      ) : (
        <ul className="lsx-tolenh">
          {items.map((r) => {
            const o = orders.get(r.order_id);
            const meta = lenhMeta(r.trang_thai);
            const pct = r.muc_tieu_sl > 0 ? Math.min(100, Math.round((r.tong_dat / r.muc_tieu_sl) * 100)) : null;
            return (
              <li key={r.id}>
                <button
                  type="button"
                  className={`lsx-tolenh__card${r.den_luot ? " is-turn" : ""}`}
                  onClick={() => onOpen(r.id)}
                >
                  <div className="lsx-tolenh__lead">
                    <div className="lsx-tolenh__idline">
                      <span className="lsx-code">{maLenh(r.id)}</span>
                      {r.den_luot ? (
                        <span className="lsx-flag">
                          <BellIcon /> Đến lượt
                        </span>
                      ) : (
                        <span className={`lsx-badge lsx-badge--${meta.variant}`}>
                          <span className="lsx-badge__d" />
                          {meta.label}
                        </span>
                      )}
                    </div>
                    <span className="lsx-tolenh__ap">{anPhamLabel(r.phieu_thanh_phan_id)}</span>
                    <span className="lsx-tolenh__cust mono">
                      {o?.customer_name ?? "—"} · {o?.order_no ?? `Đơn #${r.order_id}`}
                    </span>
                  </div>

                  <div className="lsx-tolenh__mid">
                    <div className="lsx-tolenh__steprow">
                      <span className="lsx-tolenh__steplbl">
                        Bước {r.cur_thu_tu ?? r.so_buoc}/{r.so_buoc}
                      </span>
                      <span className="lsx-tolenh__stepten">
                        {r.cur_ten ?? "Hoàn tất routing"}
                        {r.cur_to_id != null ? (
                          <span className="lsx-tolenh__at"> · {deptName(r.cur_to_id)}</span>
                        ) : null}
                      </span>
                    </div>
                    {pct != null ? (
                      <div className="lsx-prog__bar lsx-prog__bar--sm">
                        <div className="lsx-prog__fill" style={{ width: `${pct}%` }} />
                      </div>
                    ) : null}
                    <span className="lsx-tolenh__num mono">
                      {fmt(r.tong_dat)} / {r.muc_tieu_sl > 0 ? fmt(r.muc_tieu_sl) : "—"} sp
                      {r.so_buoc_xong > 0 ? ` · ${r.so_buoc_xong}/${r.so_buoc} công đoạn xong` : ""}
                    </span>
                  </div>
                  <ChevronRightIcon />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}

// ============================================================ TẦNG 3 — MÀN THỰC THI
function ExecView({
  to,
  lenhId,
  tick,
  orders,
  deptName,
  toasts,
  onBack,
  afterAction,
}: {
  to: ToNode;
  lenhId: number;
  tick: number;
  orders: Map<number, OrderRow>;
  deptName: (id: number | null) => string;
  toasts: ReturnType<typeof useToasts>;
  onBack: () => void;
  afterAction: () => void;
}) {
  const { token } = useAuth();
  const [detail, setDetail] = useState<LenhSXDetailOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyStep, setBusyStep] = useState<number | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    api.lenhSanXuat
      .get(token, lenhId)
      .then(setDetail)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không mở được lệnh."));
  }, [token, lenhId]);
  useEffect(() => {
    load();
  }, [load, tick]);

  const routing = detail?.routing ?? [];
  const curStep = useMemo(() => routing.find((s) => s.trang_thai !== "xong") ?? null, [routing]);

  async function act(step: RoutingStepRow, kind: "bat_dau" | "hoan_thanh") {
    if (!token || busyStep) return;
    setBusyStep(step.id);
    try {
      if (kind === "bat_dau") await api.lenhSanXuat.batDauBuoc(token, step.id);
      else await api.lenhSanXuat.hoanThanhBuoc(token, step.id);
      toasts.ok(kind === "bat_dau" ? `Đã bắt đầu “${step.ten}”` : `Đã hoàn thành “${step.ten}”`);
      afterAction();
      load();
    } catch (e) {
      // Cổng cứng backend (chưa tới lượt / chưa phát) → 409: hiện toast đỏ, không phán.
      toasts.err(e instanceof ApiError ? e.message : "Chưa thao tác được.");
    } finally {
      setBusyStep(null);
    }
  }

  const o = detail ? orders.get(detail.order_id) : undefined;
  const meta = detail ? lenhMeta(detail.trang_thai) : { label: "", variant: "neutral" };
  const muc = detail?.muc_tieu_sl ?? 0;
  const dat = detail?.tong_dat ?? 0;
  const pct = muc > 0 ? Math.min(100, Math.round((dat / muc) * 100)) : null;
  const xongCount = routing.filter((s) => s.trang_thai === "xong").length;
  const log = (detail?.san_luong ?? []).slice(-6).reverse();

  return (
    <main className="lsx">
      <ToastStack toasts={toasts.toasts} onDismiss={toasts.dismiss} />
      <button type="button" className="lsx-back" onClick={onBack}>
        <BackIcon /> Lệnh của {to.name}
      </button>

      {error ? (
        <div className="banner banner--error" role="alert">
          <span>{error}</span>
          <button type="button" className="btn btn--ghost" style={{ padding: "4px 12px", fontSize: 12 }} onClick={load}>
            Tải lại
          </button>
        </div>
      ) : null}

      {detail === null ? (
        <p className="lsx-msg">Đang mở lệnh…</p>
      ) : (
        <>
          {/* Header lệnh: mã (payload QR) + ấn phẩm + tiến độ */}
          <section className="lsx-exec__hd">
            <div className="lsx-exec__qr" aria-hidden="true">
              <ScanIcon />
              <span className="lsx-exec__qrcode mono">{maLenh(detail.id)}</span>
            </div>
            <div className="lsx-exec__hdmain">
              <div className="lsx-exec__hdtop">
                <h1 className="lsx-exec__title">{anPhamLabel(detail.phieu_thanh_phan_id)}</h1>
                <span className={`lsx-badge lsx-badge--${meta.variant}`}>
                  <span className="lsx-badge__d" />
                  {meta.label}
                </span>
              </div>
              <span className="lsx-exec__cust mono">
                {o?.customer_name ?? "—"} · {o?.order_no ?? `Đơn #${detail.order_id}`}
              </span>
              <div className="lsx-prog">
                <div className="lsx-prog__row">
                  <span className="lsx-prog__big">
                    {fmt(dat)}
                    <span className="u"> / {muc > 0 ? fmt(muc) : "—"} sp</span>
                  </span>
                  <span className="lsx-prog__side">
                    {pct != null ? <span className="lsx-prog__pct">{pct}%</span> : null}
                    <span className="lsx-prog__steps">{xongCount}/{routing.length} công đoạn</span>
                  </span>
                </div>
                {pct != null ? (
                  <div className="lsx-prog__bar">
                    <div className="lsx-prog__fill" style={{ width: `${pct}%` }} />
                  </div>
                ) : null}
              </div>
            </div>
          </section>

          {/* Routing dạng THẺ — chỉ thẻ của TỔ MÌNH + đúng bước đến lượt mới thao tác */}
          <section className="lsx-panel">
            <div className="lsx-panel__hd">
              <h3>
                <RouteIcon /> Công đoạn (routing)
              </h3>
              <span className="lsx-panel__hint">Thẻ viền cam = đến lượt tổ {to.name}</span>
            </div>
            {routing.length === 0 ? (
              <div className="lsx-empty lsx-empty--sm">
                <p className="lsx-empty__title">Lệnh chưa có routing.</p>
              </div>
            ) : (
              <ol className="lsx-rcards">
                {routing.map((s) => {
                  const rm = rsMeta(s.trang_thai);
                  const mine = s.to_id === to.id;
                  const isCur = curStep?.id === s.id;
                  const canAct = mine && isCur && detail.trang_thai === "dang_chay";
                  const waiting = mine && !isCur && s.trang_thai === "cho";
                  return (
                    <li
                      key={s.id}
                      className={`lsx-rcard lsx-rcard--${rm.variant}${mine ? " is-mine" : ""}${canAct ? " is-turn" : ""}`}
                    >
                      <div className="lsx-rcard__head">
                        <span className="lsx-rcard__no">{s.thu_tu}</span>
                        <span className={`lsx-badge lsx-badge--${rm.variant}`}>
                          <span className="lsx-badge__d" />
                          {rm.label}
                        </span>
                      </div>
                      <span className="lsx-rcard__ten">{s.ten || `Công đoạn #${s.cong_doan_id ?? "?"}`}</span>
                      <span className="lsx-rcard__to">
                        <UsersIcon /> {deptName(s.to_id)}
                        {mine ? <span className="lsx-rcard__mine">Tổ này</span> : null}
                      </span>
                      {(s.bat_dau_at || s.hoan_thanh_at) ? (
                        <span className="lsx-rcard__ts mono">
                          {s.bat_dau_at ? `BĐ ${fmtTime(s.bat_dau_at)}` : ""}
                          {s.hoan_thanh_at ? `${s.bat_dau_at ? " · " : ""}HT ${fmtTime(s.hoan_thanh_at)}` : ""}
                        </span>
                      ) : null}

                      {canAct ? (
                        s.trang_thai === "cho" ? (
                          <button
                            type="button"
                            className="lsx-scanbtn lsx-scanbtn--start"
                            disabled={busyStep === s.id}
                            onClick={() => act(s, "bat_dau")}
                          >
                            <ScanIcon /> {busyStep === s.id ? "Đang ghi…" : "Bắt đầu"}
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="lsx-scanbtn lsx-scanbtn--done"
                            disabled={busyStep === s.id}
                            onClick={() => act(s, "hoan_thanh")}
                          >
                            <CheckIcon /> {busyStep === s.id ? "Đang ghi…" : "Hoàn thành"}
                          </button>
                        )
                      ) : waiting ? (
                        <span className="lsx-rcard__wait">
                          <ClockIcon /> Chờ tổ trước xong
                        </span>
                      ) : null}
                    </li>
                  );
                })}
              </ol>
            )}
          </section>

          {/* Nhật ký sản lượng gần đây — MÁY CHỈ GHI NHẬN (chỉ xem) */}
          {log.length > 0 ? (
            <section className="lsx-panel">
              <div className="lsx-panel__hd">
                <h3>
                  <GaugeIcon /> Nhật ký sản lượng
                </h3>
              </div>
              <ul className="lsx-log">
                {log.map((r) => (
                  <li key={r.id} className="lsx-log__row">
                    <span className="lsx-log__to">{deptName(r.to_id)}</span>
                    <span className="lsx-log__num mono">
                      +{fmt(r.so_dat)} đạt{r.so_hong > 0 ? ` · ${fmt(r.so_hong)} hỏng` : ""}
                    </span>
                    <span className="lsx-log__at mono">{fmtTime(r.created_at)}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </>
      )}
    </main>
  );
}

function fmtTime(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  return isNaN(d.getTime()) ? "—" : d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

// ---------- Inline icons (Lucide-style, currentColor) ----------
const BackIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M15 18l-6-6 6-6" />
  </svg>
);
const ChevronRightIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lsx-chev" aria-hidden="true">
    <path d="M9 6l6 6-6 6" />
  </svg>
);
const BellIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6Z" />
    <path d="M10.5 20a1.8 1.8 0 0 0 3 0" />
  </svg>
);
const UsersIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="9" cy="8" r="3.2" />
    <path d="M3.5 20a5.5 5.5 0 0 1 11 0" />
    <path d="M16 5.2a3 3 0 0 1 0 5.6M17.5 20a5.5 5.5 0 0 0-3-4.9" />
  </svg>
);
const FactoryIcon = () => (
  <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" className="lsx-empty__icon" aria-hidden="true">
    <path d="M3 20V9l6 4V9l6 4V5h4a2 2 0 0 1 2 2v13Z" />
    <path d="M7 20v-4M12 20v-4M17 20v-4" />
  </svg>
);
const InboxIcon = () => (
  <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" className="lsx-empty__icon" aria-hidden="true">
    <path d="M22 12h-6l-2 3h-4l-2-3H2" />
    <path d="M5.5 6.5 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-5.5A2 2 0 0 0 16.8 5.6H7.2A2 2 0 0 0 5.5 6.5Z" />
  </svg>
);
const ScanIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2" />
    <path d="M4 12h16" />
  </svg>
);
const CheckIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20 6 9 17l-5-5" />
  </svg>
);
const ClockIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </svg>
);
const RouteIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="6" cy="19" r="2.4" />
    <circle cx="18" cy="5" r="2.4" />
    <path d="M8.4 19H14a3.5 3.5 0 0 0 0-7h-4a3.5 3.5 0 0 1 0-7h5.6" />
  </svg>
);
const GaugeIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 14 15 9" />
    <path d="M3.5 18a9 9 0 1 1 17 0" />
    <circle cx="12" cy="14" r="1.4" fill="currentColor" stroke="none" />
  </svg>
);
