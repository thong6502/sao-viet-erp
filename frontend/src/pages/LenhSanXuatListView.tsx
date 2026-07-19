// MASTER của "Kế hoạch sản xuất" — danh sách LỆNH SẢN XUẤT. Bấm dòng → detail lệnh.
// API record-only (máy chỉ ghi): list trả ID mềm (đơn/ấn phẩm/máy) → resolve tên qua danh mục
// (orders · máy) như PTG resolve giấy/máy. Lọc trạng thái + search client-side (bám PhieuTinhGiaListView).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  ApiError,
  connectQuoteEvents,
  type CongDoanLite,
  type HangChoDon,
  type LenhSXRow,
  type OrderRow,
} from "../api/client";
import { mayThietBi, type Row } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import { StatusTabs } from "../components/StatusTabs";
import { AnPhamDrawer } from "./AnPhamDrawer";
import { ToastStack, useToasts } from "./LsxToast";
import { hanGiao } from "../utils/format";
import "./lenh-san-xuat.css";

// Trạng thái lệnh (suy ra ở BE, record-only) → nhãn + biến thể badge (màu app).
const LENH_META: Record<string, { label: string; variant: string }> = {
  nhap: { label: "Nháp", variant: "neutral" },
  dang_chay: { label: "Đang chạy", variant: "run" },
  xong: { label: "Xong", variant: "done" },
  huy: { label: "Hủy", variant: "danger" },
};
function lenhMeta(tt: string): { label: string; variant: string } {
  return LENH_META[tt] ?? { label: tt || "—", variant: "neutral" };
}

const maLenh = (id: number): string => `LSX-${String(id).padStart(4, "0")}`;

function fmtDate(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("vi-VN");
}

const anPhamLabel = (id: number | null): string =>
  id ? `Ấn phẩm #${id}` : "— chưa gắn ấn phẩm";

export function LenhSanXuatListView({
  onOpen,
  onGhep,
  onLich,
}: {
  onOpen: (id: number) => void;
  onGhep: () => void;
  onLich: () => void;
}) {
  const { token } = useAuth();
  const { toasts, ok: toastOk, err: toastErr, dismiss: toastDismiss } = useToasts();
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [items, setItems] = useState<LenhSXRow[]>([]);
  const [orders, setOrders] = useState<Map<number, OrderRow>>(new Map());
  const [mays, setMays] = useState<Map<number, Row>>(new Map());
  const [congDoans, setCongDoans] = useState<Map<number, CongDoanLite>>(new Map());
  const [hangCho, setHangCho] = useState<HangChoDon[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("cho_kh");
  // Chọn ấn phẩm (ptpId) để Gộp / Tách thành lệnh nháp; + drawer chi tiết ấn phẩm.
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [taoBusy, setTaoBusy] = useState(false);
  const [drawer, setDrawer] = useState<{ ptpId: number; orderNo: string; khach: string | null } | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q.trim().toLowerCase()), 200);
    return () => clearTimeout(t);
  }, [q]);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    Promise.all([
      api.lenhSanXuat.list(token, {}),
      api.orders.list(token, { size: 200 }).catch(() => ({ items: [] as OrderRow[] })),
      mayThietBi.list(token).catch(() => ({ items: [] as Row[] })),
      api.lenhSanXuat.hangCho(token).catch(() => [] as HangChoDon[]),
      api.congDoan.list(token).catch(() => ({ items: [] as CongDoanLite[] })),
    ])
      .then(([lenh, ord, may, hc, cd]) => {
        setItems(lenh.items);
        setOrders(new Map(ord.items.map((o) => [o.id, o])));
        setMays(new Map(may.items.map((m) => [m.id, m])));
        setCongDoans(new Map(cd.items.map((c) => [c.id, c])));
        setHangCho(hc);
        // SSE/refetch: giữ selection cho ptp CÒN TỒN TẠI, bỏ ptp đã lên lệnh.
        const valid = new Set<number>();
        hc.forEach((d) =>
          d.an_pham.forEach((a) => a.phieu_thanh_phan_id != null && valid.add(a.phieu_thanh_phan_id)),
        );
        setSelected((prev) => {
          const next = new Set<number>();
          prev.forEach((p) => valid.has(p) && next.add(p));
          return next.size === prev.size ? prev : next;
        });
      })
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Không tải được danh sách lệnh sản xuất."),
      )
      .finally(() => setLoading(false));
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

  // Real-time handoff: đơn chốt 'bắn xuống' hàng chờ; Sale đổi gấp/lưu ý sau chốt → badge nhảy + toast.
  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => {
    if (!token) return;
    return connectQuoteEvents(token, (e) => {
      if (e.type === "order_ordered") {
        loadRef.current();
        toastOk("🔔 Đơn mới chờ lên kế hoạch");
      } else if (e.type === "order_sx_hint_changed") {
        loadRef.current();
        toastOk(e.is_rush ? "⚡ Một đơn vừa chuyển GẤP" : "Cập nhật lưu ý sản xuất");
      }
    });
  }, [token, toastOk]);

  const mayName = useCallback(
    (id: number | null): string | null => {
      if (id == null) return null;
      const m = mays.get(id);
      return m ? String(m.ten ?? m.ma ?? `#${id}`) : `Máy #${id}`;
    },
    [mays],
  );
  const cdName = useCallback(
    (id: number | null): string => {
      if (id == null) return "—";
      const c = congDoans.get(id);
      return c ? c.ten : `Công đoạn #${id}`;
    },
    [congDoans],
  );

  // ptp → đơn (để biết chọn có cùng 1 đơn không → cho phép Gộp).
  const ptpOrder = useMemo(() => {
    const m = new Map<number, { orderId: number; orderNo: string }>();
    hangCho.forEach((d) =>
      d.an_pham.forEach((a) => {
        if (a.phieu_thanh_phan_id != null)
          m.set(a.phieu_thanh_phan_id, { orderId: d.order_id, orderNo: d.order_no });
      }),
    );
    return m;
  }, [hangCho]);

  const selOrderIds = useMemo(() => {
    const s = new Set<number>();
    selected.forEach((p) => {
      const o = ptpOrder.get(p);
      if (o) s.add(o.orderId);
    });
    return s;
  }, [selected, ptpOrder]);
  const sameOrder = selOrderIds.size === 1;
  const soleOrderNo = useMemo(() => {
    if (!sameOrder) return null;
    const first = [...selected][0];
    return first != null ? ptpOrder.get(first)?.orderNo ?? null : null;
  }, [sameOrder, selected, ptpOrder]);

  const toggleAp = useCallback((ptpId: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(ptpId)) next.delete(ptpId);
      else next.add(ptpId);
      return next;
    });
  }, []);
  // Chọn/bỏ cả đơn: tick mọi ấn phẩm (có ptp) của đơn; indeterminate khi chọn 1 phần.
  const toggleOrder = useCallback((hc: HangChoDon) => {
    const ids = hc.an_pham
      .map((a) => a.phieu_thanh_phan_id)
      .filter((x): x is number => x != null);
    setSelected((prev) => {
      const next = new Set(prev);
      const allOn = ids.length > 0 && ids.every((id) => next.has(id));
      if (allOn) ids.forEach((id) => next.delete(id));
      else ids.forEach((id) => next.add(id));
      return next;
    });
  }, []);

  // Gộp = 1 lệnh (mọi ptp cùng 1 đơn) · Tách = mỗi ptp 1 lệnh (gom theo đơn). Sau thành công:
  // bỏ ap đã lên lệnh khỏi hàng chờ, clear chọn, toast, reload để badge tab Nháp nhảy — Ở LẠI cho_kh.
  const createLenh = useCallback(
    async (mode: "gop" | "tach") => {
      if (!token || taoBusy || selected.size === 0) return;
      const ptps = [...selected];
      const byOrder = new Map<number, number[]>();
      for (const p of ptps) {
        const o = ptpOrder.get(p);
        if (o == null) continue;
        const arr = byOrder.get(o.orderId);
        if (arr) arr.push(p);
        else byOrder.set(o.orderId, [p]);
      }
      if (byOrder.size === 0) return;
      if (mode === "gop" && byOrder.size !== 1) return; // an toàn: Gộp chỉ trong 1 đơn
      setTaoBusy(true);
      try {
        let n = 0;
        if (mode === "gop") {
          const [orderId, ps] = [...byOrder.entries()][0];
          await api.lenhSanXuat.taoLenh(token, orderId, ps);
          n = 1;
        } else {
          for (const [orderId, ps] of byOrder) {
            for (const p of ps) {
              await api.lenhSanXuat.taoLenh(token, orderId, [p]);
              n += 1;
            }
          }
        }
        const done = new Set(ptps);
        setHangCho((hc) =>
          hc
            .map((d) => ({
              ...d,
              an_pham: d.an_pham.filter(
                (a) => a.phieu_thanh_phan_id == null || !done.has(a.phieu_thanh_phan_id),
              ),
            }))
            .filter((d) => d.an_pham.length > 0),
        );
        setSelected(new Set());
        toastOk(`Đã tạo ${n} lệnh nháp — xem tab Nháp`);
        load();
      } catch (e) {
        toastErr(e instanceof ApiError ? e.message : "Không tạo được lệnh.");
      } finally {
        setTaoBusy(false);
      }
    },
    [token, taoBusy, selected, ptpOrder, load, toastOk, toastErr],
  );

  const filtered = useMemo(() => {
    let rows = items;
    if (statusFilter !== "all") rows = rows.filter((r) => r.trang_thai === statusFilter);
    if (debouncedQ) {
      rows = rows.filter((r) => {
        const o = orders.get(r.order_id);
        const hay = [
          maLenh(r.id),
          o?.order_no ?? "",
          o?.customer_name ?? "",
          mayName(r.may_id) ?? "",
          r.phieu_thanh_phan_id ? `ấn phẩm ${r.phieu_thanh_phan_id}` : "",
        ]
          .join(" ")
          .toLowerCase();
        return hay.includes(debouncedQ);
      });
    }
    // Đang chạy trước (việc cần theo), rồi nháp, xong, hủy; trong nhóm mới cập nhật lên đầu.
    const order: Record<string, number> = { dang_chay: 0, nhap: 1, xong: 2, huy: 3 };
    return [...rows].sort((a, b) => {
      const d = (order[a.trang_thai] ?? 9) - (order[b.trang_thai] ?? 9);
      if (d !== 0) return d;
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
    });
  }, [items, statusFilter, debouncedQ, orders, mayName]);

  const count = (tt: string) => items.filter((r) => r.trang_thai === tt).length;

  const hcFiltered = useMemo(() => {
    if (!debouncedQ) return hangCho;
    return hangCho.filter((h) =>
      [h.order_no, h.khach ?? "", h.an_pham.map((a) => a.description).join(" ")]
        .join(" ")
        .toLowerCase()
        .includes(debouncedQ),
    );
  }, [hangCho, debouncedQ]);

  return (
    <main className="lsx">
      <header className="lsx-head">
        <div className="lsx-head__lead">
          <div className="lsx-eyebrow">
            <span className="sq" /> Sản xuất · Kế hoạch
          </div>
          <h1 className="lsx-head__title">Kế hoạch sản xuất</h1>
          <p className="lsx-head__sub">
            Lệnh sản xuất suy từ đơn đã chốt — theo dõi duyệt mẫu, ghép tờ in, sản lượng &amp; giao
            nhận giữa các tổ.
          </p>
        </div>
        <div className="lsx-head__actions">
          <button type="button" className="btn btn--secondary" onClick={onLich}>
            <CalendarIcon /> Lịch chạy
          </button>
          <button type="button" className="btn btn--primary" onClick={onGhep}>
            <PlusLayersIcon /> Ghép bài
          </button>
        </div>
      </header>

      <div className="lsx-toolbar">
        <div className="lsx-search">
          <SearchIcon />
          <input
            className="lsx-search__input"
            placeholder="Tìm mã lệnh, đơn hàng, khách, máy…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Tìm lệnh sản xuất"
          />
        </div>
      </div>

      <div className="lsx-tabrow">
        <StatusTabs
          tabs={[
            { key: "cho_kh", label: "Chờ lên kế hoạch", count: hangCho.length },
            { key: "all", label: "Tất cả", count: items.length },
            { key: "dang_chay", label: "Đang chạy", count: count("dang_chay") },
            { key: "nhap", label: "Nháp", count: count("nhap") },
            { key: "xong", label: "Xong", count: count("xong") },
            { key: "huy", label: "Hủy", count: count("huy") },
          ]}
          active={statusFilter}
          onChange={setStatusFilter}
        />
      </div>

      {error ? (
        <div className="banner banner--error" role="alert" style={{ marginTop: "var(--sp-2)" }}>
          <span>{error}</span>
          <button
            type="button"
            className="btn btn--ghost"
            style={{ padding: "4px 12px", fontSize: "12px" }}
            onClick={load}
          >
            Tải lại
          </button>
        </div>
      ) : null}

      {statusFilter === "cho_kh" ? (
        loading ? (
          <div className="lsx-msg" style={{ padding: "var(--sp-6)" }}>Đang tải dữ liệu…</div>
        ) : hcFiltered.length === 0 ? (
          <div className="lsx-empty">
            <InboxIcon />
            <p className="lsx-empty__title">
              {debouncedQ ? "Không có đơn chờ phù hợp." : "Chưa có đơn nào chờ lên kế hoạch."}
            </p>
            <p className="lsx-empty__sub">
              Đơn bán vừa chốt hiện ở đây (real-time). Tick ấn phẩm rồi <b>Gộp</b> thành 1 lệnh hoặc{" "}
              <b>Tách</b> mỗi ấn phẩm 1 lệnh.
            </p>
          </div>
        ) : (
          <>
            <ul className={`lsx-book${selected.size > 0 ? " lsx-book--pad" : ""}`}>
              {hcFiltered.map((hc) => {
                const due = hanGiao(hc.delivery_committed_date);
                const ids = hc.an_pham
                  .map((a) => a.phieu_thanh_phan_id)
                  .filter((x): x is number => x != null);
                const selCount = ids.filter((id) => selected.has(id)).length;
                const allOn = ids.length > 0 && selCount === ids.length;
                const someOn = selCount > 0 && !allOn;
                return (
                  <li key={hc.order_id} className={`lsx-book__group${hc.is_rush ? " is-rush" : ""}`}>
                    <div className="lsx-book__ghd">
                      <div className="lsx-book__ghdl">
                        <button
                          type="button"
                          className={`lsx-check${allOn ? " is-on" : someOn ? " is-mixed" : ""}`}
                          role="checkbox"
                          aria-checked={allOn ? "true" : someOn ? "mixed" : "false"}
                          aria-label={`Chọn cả đơn ${hc.order_no}`}
                          disabled={ids.length === 0}
                          onClick={() => toggleOrder(hc)}
                        >
                          {allOn ? <CheckIcon /> : someOn ? <DashIcon /> : null}
                        </button>
                        <div className="lsx-book__idblk">
                          <span className="lsx-book__khach">{hc.khach ?? "— khách chưa gán"}</span>
                          <span className="lsx-book__ma">{hc.order_no}</span>
                        </div>
                      </div>
                      <div className="lsx-book__ghdr">
                        {due ? (
                          <span className={`lsx-due lsx-due--${due.level}`}>
                            <ClockIcon /> {due.label}
                          </span>
                        ) : null}
                        {hc.is_rush ? (
                          <span className="lsx-badge lsx-badge--danger">
                            <ZapIcon /> GẤP
                          </span>
                        ) : null}
                      </div>
                    </div>
                    {hc.production_note ? (
                      <div className="lsx-book__note">
                        <NoteIcon />
                        <span>
                          <strong>Lưu ý SX:</strong> {hc.production_note}
                        </span>
                      </div>
                    ) : null}
                    <div className="lsx-book__rows">
                      {hc.an_pham.map((a, i) => {
                        const ptp = a.phieu_thanh_phan_id;
                        const on = ptp != null && selected.has(ptp);
                        const chips = (a.spec_tom_tat || "")
                          .split(" · ")
                          .map((s) => s.trim())
                          .filter(Boolean);
                        const open = () => {
                          if (ptp != null)
                            setDrawer({ ptpId: ptp, orderNo: hc.order_no, khach: hc.khach });
                        };
                        return (
                          <div
                            key={ptp ?? `x${i}`}
                            className={`lsx-rec${on ? " is-sel" : ""}`}
                            role="button"
                            tabIndex={ptp != null ? 0 : -1}
                            onClick={open}
                            onKeyDown={(e) => {
                              if (ptp != null && (e.key === "Enter" || e.key === " ")) {
                                e.preventDefault();
                                open();
                              }
                            }}
                          >
                            <div className="lsx-rec__checkcell">
                              <button
                                type="button"
                                className={`lsx-check${on ? " is-on" : ""}`}
                                role="checkbox"
                                aria-checked={on}
                                aria-label={`Chọn ${a.description || "ấn phẩm"}`}
                                disabled={ptp == null}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (ptp != null) toggleAp(ptp);
                                }}
                              >
                                {on ? <CheckIcon /> : null}
                              </button>
                            </div>
                            <div className="lsx-rec__nameblk">
                              <span className="lsx-rec__name">
                                {a.description || anPhamLabel(ptp)}
                              </span>
                            </div>
                            <div className="lsx-rec__qty">
                              <span className="lsx-rec__qtyn">{a.qty.toLocaleString("vi-VN")}</span>
                              <span className="lsx-rec__qtyu">{a.don_vi_tinh}</span>
                            </div>
                            <div className="lsx-rec__chips">
                              {chips.map((c, ci) => (
                                <span className="lsx-specchip" key={ci}>
                                  <span className="lsx-specchip__v">{c}</span>
                                </span>
                              ))}
                            </div>
                            <span className="lsx-rec__chev" aria-hidden="true">
                              <ChevIcon />
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </li>
                );
              })}
            </ul>

            {selected.size > 0 ? (
              <div className="lsx-actionbar">
                <div className="lsx-actionbar__l">
                  <span className="lsx-actionbar__ic">
                    <CheckDot />
                  </span>
                  <div className="lsx-actionbar__txt">
                    <span className="lsx-actionbar__n">Đã chọn {selected.size} ấn phẩm</span>
                    <span
                      className={`lsx-actionbar__sub lsx-actionbar__sub--${sameOrder ? "same" : "multi"}`}
                    >
                      {sameOrder ? `cùng đơn ${soleOrderNo ?? ""}` : `thuộc ${selOrderIds.size} đơn`}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="lsx-actionbar__clear"
                    onClick={() => setSelected(new Set())}
                  >
                    Bỏ chọn
                  </button>
                </div>
                <div className="lsx-actionbar__r">
                  <button
                    type="button"
                    className="btn btn--secondary"
                    disabled={taoBusy}
                    onClick={() => createLenh("tach")}
                  >
                    <PlusLayersIcon /> Mỗi ấn phẩm 1 lệnh
                  </button>
                  <button
                    type="button"
                    className="btn btn--primary"
                    disabled={taoBusy || !sameOrder}
                    onClick={() => createLenh("gop")}
                    title={
                      sameOrder
                        ? "Gộp các ấn phẩm đã chọn thành 1 lệnh"
                        : "Chỉ gộp được khi các ấn phẩm cùng 1 đơn"
                    }
                  >
                    <LayersIcon /> {taoBusy ? "Đang tạo…" : "Gộp thành 1 lệnh"}
                  </button>
                  {!sameOrder ? (
                    <p className="lsx-actionbar__reason">
                      Chỉ gộp trong cùng 1 đơn — dùng <b>Mỗi ấn phẩm 1 lệnh</b>, hoặc ghép xuyên đơn ở
                      Ghép bài.
                    </p>
                  ) : null}
                </div>
              </div>
            ) : null}
          </>
        )
      ) : (
      <>
      <div className="lsx-tablewrap">
        <table className="lsx-table">
          <thead>
            <tr>
              <th>Lệnh · Ấn phẩm</th>
              <th>Đơn hàng · Khách</th>
              <th>Máy</th>
              <th>Duyệt mẫu</th>
              <th>Trạng thái</th>
              <th>Hạn giao</th>
              <th>Cập nhật</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="lsx-msg">
                  Đang tải dữ liệu…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: 0 }}>
                  <div className="lsx-empty">
                    <EmptyIcon />
                    <p className="lsx-empty__title">
                      {debouncedQ || statusFilter !== "all"
                        ? "Không có lệnh phù hợp bộ lọc."
                        : "Chưa có lệnh sản xuất nào."}
                    </p>
                    <p className="lsx-empty__sub">
                      Đơn đã chốt hiện ở tab “Chờ lên kế hoạch” — bấm “Lên kế hoạch” để đề lệnh (mỗi
                      ấn phẩm = 1 lệnh).
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              filtered.map((r) => {
                const o = orders.get(r.order_id);
                const meta = lenhMeta(r.trang_thai);
                const my = mayName(r.may_id);
                return (
                  <tr
                    key={r.id}
                    className="lsx-row"
                    role="button"
                    tabIndex={0}
                    onClick={() => onOpen(r.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onOpen(r.id);
                      }
                    }}
                  >
                    <td>
                      <div className="lsx-cellstack">
                        <span className="lsx-code">{maLenh(r.id)}</span>
                        <span className="lsx-cellstack__sub mono">
                          {r.phieu_thanh_phan_id ? `Ấn phẩm #${r.phieu_thanh_phan_id}` : "— chưa gắn ấn phẩm"}
                        </span>
                      </div>
                    </td>
                    <td>
                      <div className="lsx-cellstack">
                        <span className="lsx-cellstack__main">{o?.customer_name ?? "—"}</span>
                        <span className="lsx-cellstack__sub mono">{o?.order_no ?? `Đơn #${r.order_id}`}</span>
                      </div>
                    </td>
                    <td>
                      {my ? (
                        <span className="mono" style={{ fontSize: 12.5 }}>{my}</span>
                      ) : (
                        <span className="muted">— chưa gán</span>
                      )}
                    </td>
                    <td>
                      {r.mau_approved_at ? (
                        <span className="lsx-stampchip lsx-stampchip--on">
                          <SealIcon /> Đã duyệt
                        </span>
                      ) : (
                        <span className="lsx-stampchip lsx-stampchip--off">
                          <ClockIcon /> Chờ duyệt
                        </span>
                      )}
                    </td>
                    <td>
                      <span className={`lsx-badge lsx-badge--${meta.variant}`}>
                        <span className="lsx-badge__d" />
                        {meta.label}
                      </span>
                    </td>
                    <td>
                      {(() => {
                        const nb = hanGiao(r.han_giao_noi_bo ?? r.han_giao_khach);
                        const showKH = !!r.han_giao_noi_bo && !!r.han_giao_khach;
                        return (
                          <div className="lsx-duestack">
                            {nb ? (
                              <span className={`lsx-due lsx-due--${nb.level}`}><ClockIcon /> {nb.label}</span>
                            ) : (
                              <span className="muted">—</span>
                            )}
                            {showKH && (
                              <span className="lsx-hardline"><FlagIcon /> Khách <b>{fmtDate(r.han_giao_khach)}</b></span>
                            )}
                            {o?.is_rush && (
                              <span className="lsx-rush"><ZapIcon /> Gấp</span>
                            )}
                          </div>
                        );
                      })()}
                    </td>
                    <td>
                      <span className="mono" style={{ fontSize: 12, color: "var(--ash)" }}>
                        {fmtDate(r.updated_at)}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {!loading && filtered.length > 0 ? (
        <p className="lsx-foot-note">
          {filtered.length} lệnh trong bộ lọc hiện tại · tổng {items.length} lệnh.
        </p>
      ) : null}
      </>
      )}

      {drawer && token ? (
        <AnPhamDrawer
          token={token}
          ptpId={drawer.ptpId}
          ctx={{ orderNo: drawer.orderNo, khach: drawer.khach ?? undefined }}
          cdName={cdName}
          mayName={mayName}
          onClose={() => setDrawer(null)}
        />
      ) : null}

      <ToastStack toasts={toasts} onDismiss={toastDismiss} />
    </main>
  );
}

// ---------- Inline icons (Lucide-style, 1.75 stroke, currentColor) ----------
const SearchIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" className="lsx-search__icon" aria-hidden="true">
    <circle cx="11" cy="11" r="8" />
    <path d="m21 21-4.3-4.3" />
  </svg>
);
const SealIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 2.6 5 5.4v5.2c0 4.3 3 7.6 7 8.8 4-1.2 7-4.5 7-8.8V5.4L12 2.6Z" />
    <path d="m9 11.6 2 2 4-4.2" />
  </svg>
);
const ClockIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </svg>
);
const ZapIcon = () => (
  <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" stroke="none" aria-hidden="true">
    <path d="M13 2 4.5 13.2h6.2L10 22l8.5-11.2h-6.2Z" />
  </svg>
);
const FlagIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
    <path d="M4 22v-7" />
  </svg>
);
const EmptyIcon = () => (
  <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" className="lsx-empty__icon" aria-hidden="true">
    <rect x="5" y="4.5" width="14" height="16.5" rx="2" />
    <rect x="8.75" y="2.5" width="6.5" height="3.8" rx="1.2" />
    <path d="M9 11h6M9 14.6h6M9 18.2h3.5" />
  </svg>
);
const PlusLayersIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m12 3 9 5-9 5-9-5 9-5Z" />
    <path d="m3 13 9 5 5-2.8" />
    <path d="M18 14v6M15 17h6" />
  </svg>
);
const CalendarIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="3.5" y="5" width="17" height="16" rx="2" />
    <path d="M3.5 9.5h17M8 3v4M16 3v4" />
  </svg>
);
const NoteIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M15.5 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L15.5 3Z" />
    <path d="M15 3v5h5M8.5 12.5h7M8.5 16h5" />
  </svg>
);
const CheckIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20 6 9 17l-5-5" />
  </svg>
);
const DashIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M6 12h12" />
  </svg>
);
const ChevIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m9 6 6 6-6 6" />
  </svg>
);
const CheckDot = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="9" />
    <path d="m8.5 12 2.5 2.5 4.5-5" />
  </svg>
);
const LayersIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m12 3 9 5-9 5-9-5 9-5Z" />
    <path d="m3 13 9 5 9-5" />
  </svg>
);
const InboxIcon = () => (
  <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" className="lsx-empty__icon" aria-hidden="true">
    <path d="M4 13.5 6.5 6h11L20 13.5" />
    <path d="M4 13.5V19a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5.5" />
    <path d="M4 13.5h4l1.5 2.2h5L16 13.5h4" />
  </svg>
);
