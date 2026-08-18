// BÀN KẾ HOẠCH SẢN XUẤT — controller master↔detail (không react-router, điều hướng bằng state).
//
// Luồng: Sale bấm "Chuyển xuống sản xuất" ở Đơn hàng → đơn rơi vào tab HÀNG CHỜ (real-time qua SSE,
// `eventTick` đổi → refetch) → mở đơn xem DANH SÁCH LỆNH DỰ KIẾN → tick → tạo lệnh → sang tab LỆNH
// SẢN XUẤT sửa routing/số lượng → đánh dấu "Sẵn sàng lập kế hoạch".
//
// Lát này DỪNG ở trạng thái "sẵn sàng": chưa ghép bài, chưa xếp lịch, chưa phát xuống xưởng.
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  api,
  type HangChoItem,
  type LsxListItem,
  type LsxTongQuanOut,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan, useScopeOf } from "../auth/permissions";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { Pager, trangHopLe } from "../components/Pager";
import { StatusTabs } from "../components/StatusTabs";
import { LsxDetailView } from "./LsxDetailView";
import { LsxPreviewDrawer } from "./LsxPreviewDrawer";
import { nhanDonVi } from "./lsxBuoc";
import { useNapTenDonVi } from "./tenDonVi";
import {
  BangLoi,
  ChipGap,
  DenTienDo,
  EmptyState,
  Skeleton,
  TRANG_THAI_TABS,
  TrangThaiPill,
  classHan,
  classHanLich,
  ngay,
  ngayGio,
  num,
} from "./keHoachSxShared";

/** Dòng/trang cho CẢ hai bảng của màn. Khớp mặc định `size` của `/api/lsx`; đổi ở đây là
 *  đổi cả chân trang lẫn tham số gửi lên, không được để hai nơi lệch nhau. */
const SIZE_TRANG = 50;
import "./ke-hoach-sx.css";

type View = { mode: "list" } | { mode: "detail"; id: number };

export function KeHoachSXPage({
  navigate,
  openOrderId,
  openLsxId,
  eventTick,
  onBadgeStale,
}: {
  navigate?: (id: string, params?: Record<string, unknown>) => void;
  /** Deep-link từ Đơn hàng: mở thẳng hàng chờ + drawer lệnh dự kiến của đơn này. */
  openOrderId?: number | null;
  /** Deep-link từ sơ đồ Bài ghép: mở thẳng chi tiết MỘT lệnh. */
  openLsxId?: number | null;
  /** Tăng mỗi lần có event SSE → refetch (real-time, không bắt người dùng F5). */
  eventTick?: number;
  onBadgeStale?: () => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  const scopeOf = useScopeOf();
  const canCreate = can("san_xuat", "create");
  // Nhãn đơn vị đọc từ DANH MỤC — nạp một lần cho cả phiên (bảng lệnh + drawer lệnh dự kiến).
  useNapTenDonVi();

  const [view, setView] = useState<View>({ mode: "list" });
  // Tab "Vật tư" ĐÃ TÁCH 17/08/2026 thành màn riêng `Kế hoạch vật tư` (chủ chốt) — xem
  // `KeHoachVatTuPage`. Màn này giữ đúng phạm vi MỘT lệnh; bảng cân đối cả kho là việc của màn kia.
  const [tab, setTab] = useState<"hang-cho" | "lenh">("hang-cho");
  const [previewOrderId, setPreviewOrderId] = useState<number | null>(null);
  const [orderFilter, setOrderFilter] = useState<{ id: number; code: string } | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const [queue, setQueue] = useState<HangChoItem[] | null>(null);
  const [lenhs, setLenhs] = useState<LsxListItem[] | null>(null);
  const [ttFilter, setTtFilter] = useState("all");
  const [q, setQ] = useState("");
  const [err, setErr] = useState<string | null>(null);
  // Phân trang + số trên tab đều do MÁY CHỦ trả. Đếm bằng `lenhs.length` như trước chỉ đúng khi
  // cả bảng nằm gọn trong một lượt tải — có phân trang là số đó thành số của TRANG, sai ngay.
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [facets, setFacets] = useState<Record<string, number>>({});
  const [queuePage, setQueuePage] = useState(1);
  const [queueTotal, setQueueTotal] = useState(0);
  // Hàng đèn tiến độ (Đợt 1 redesign 18/08/2026) — GỌI RỜI sau bảng lệnh, không nhét vào
  // `/api/lsx`: endpoint tổng quan chạy engine cân đối vật tư + bộ dò vấn đề, còn bảng lệnh phải
  // hiện ngay. `denTick` để các hành động khác (tạo lệnh, đổi routing, giữ chỗ) bắt đèn tính lại —
  // bộ lọc/ô tìm KHÔNG bắt, vì khoá dưới đây chỉ đổi khi TẬP lệnh đổi.
  const [tq, setTq] = useState<Record<number, LsxTongQuanOut["items"][number]>>({});
  const [denTick, setDenTick] = useState(0);

  const loadQueue = useCallback(() => {
    if (!token) return;
    api.lsx
      .hangCho(token, { page: queuePage, size: SIZE_TRANG })
      .then((r) => {
        setQueue(r.items);
        setQueueTotal(r.total);
        const ve = trangHopLe(queuePage, r.total, SIZE_TRANG);
        if (ve) setQueuePage(ve);
      })
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)));
  }, [token, queuePage]);

  const loadLenhs = useCallback(() => {
    if (!token) return;
    api.lsx
      .list(token, {
        order_id: orderFilter?.id,
        trang_thai: ttFilter === "all" ? undefined : ttFilter,
        q: q.trim() || undefined,
        page,
        size: SIZE_TRANG,
      })
      .then((r) => {
        setLenhs(r.items);
        setTotal(r.total);
        setFacets(r.facets);
        // Xoá nốt dòng cuối của trang 3 ⇒ còn 2 trang: không kéo về thì màn trắng trơn.
        const ve = trangHopLe(page, r.total, SIZE_TRANG);
        if (ve) setPage(ve);
      })
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)));
  }, [token, orderFilter, ttFilter, q, page]);

  // Đổi bộ lọc thì về trang 1 — giữ nguyên trang cũ là rơi vào vùng trống của kết quả mới.
  useEffect(() => setPage(1), [ttFilter, q, orderFilter]);

  useEffect(() => loadQueue(), [loadQueue, eventTick]);
  useEffect(() => {
    const t = setTimeout(loadLenhs, q ? 250 : 0);   // debounce ô tìm
    return () => clearTimeout(t);
  }, [loadLenhs, eventTick, q]);

  // Lệnh Nháp chưa có gì để nói (chưa chốt routing, chưa giữ chỗ) ⇒ không hỏi đèn cho chúng.
  const khoaDen = (lenhs ?? [])
    .filter((l) => l.trang_thai !== "nhap" && l.trang_thai !== "cho_bo_sung")
    .map((l) => l.id)
    .join(",");
  useEffect(() => {
    if (!token || !khoaDen) {
      setTq({});
      return;
    }
    let huy = false;
    api.lsx
      .tongQuan(token, khoaDen.split(",").map(Number))
      .then((r) => {
        if (!huy) setTq(Object.fromEntries(r.items.map((i) => [i.lsx_id, i])));
      })
      // Đèn hỏng thì bảng lệnh vẫn phải dùng được — ô đèn để trống, KHÔNG chặn cả màn bằng `err`.
      .catch(() => {
        if (!huy) setTq({});
      });
    return () => {
      huy = true;
    };
  }, [token, khoaDen, eventTick, denTick]);

  // Deep-link từ màn Đơn hàng ("Mở bàn Kế hoạch sản xuất ↗").
  useEffect(() => {
    if (openOrderId) {
      setView({ mode: "list" });
      setTab("hang-cho");
      setPreviewOrderId(openOrderId);
    }
  }, [openOrderId]);

  useEffect(() => {
    if (openLsxId) setView({ mode: "detail", id: openLsxId });
  }, [openLsxId]);

  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), 5000);
    return () => clearTimeout(t);
  }, [flash]);

  function sauKhiTao(orderId: number, maList: string[]) {
    const dh = queue?.find((o) => o.order_id === orderId);
    setPreviewOrderId(null);
    setOrderFilter({ id: orderId, code: dh?.order_no ?? `#${orderId}` });
    setTab("lenh");
    if (maList.length) setFlash(`Đã tạo ${maList.length} lệnh: ${maList.join(", ")}`);
    loadQueue();
    loadLenhs();
    onBadgeStale?.();
  }

  const doiDuLieu = useCallback(() => {
    loadQueue();
    loadLenhs();
    // Tập lệnh có thể KHÔNG đổi sau một lần sửa routing/giữ chỗ ⇒ `khoaDen` đứng yên ⇒ effect trên
    // không chạy lại. Tick thẳng để đèn không nói chuyện cũ.
    setDenTick((n) => n + 1);
    onBadgeStale?.();
  }, [loadQueue, loadLenhs, onBadgeStale]);

  if (view.mode === "detail") {
    return (
      <main className="khsx">
        <LsxDetailView
          lsxId={view.id}
          navigate={navigate}
          onBack={() => setView({ mode: "list" })}
          onChanged={doiDuLieu}
          eventTick={eventTick}
        />
      </main>
    );
  }

  // Số trên tab lấy từ `facets` của máy chủ, KHÔNG đếm mảng đang hiện. Tab gộp nhiều trạng thái
  // (Nháp = "nhap,cho_bo_sung") thì cộng các phần.
  const demTheoTt = (key: string) =>
    key === "all"
      ? (facets.all ?? 0)
      : key.split(",").reduce((s, k) => s + (facets[k] ?? 0), 0);

  return (
    <main className="khsx">
      <header className="khsx__head">
        <p className="eyebrow">Sản xuất</p>
        <div className="khsx__headrow">
          <h1 className="khsx__title">Kế hoạch sản xuất</h1>
          <span className="khsx__count">
            {num(queueTotal)} đơn chờ · {num(total)} lệnh
          </span>
        </div>
      </header>

      <div className="khsx__segrow" role="tablist" aria-label="Khu vực làm việc">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "hang-cho"}
          className={`seg ${tab === "hang-cho" ? "is-active" : ""}`}
          onClick={() => setTab("hang-cho")}
        >
          Hàng chờ
          {queueTotal > 0 && <span className="chip-count chip-count--alert">{queueTotal}</span>}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "lenh"}
          className={`seg ${tab === "lenh" ? "is-active" : ""}`}
          onClick={() => setTab("lenh")}
        >
          Lệnh sản xuất
          <span className="chip-count">{total}</span>
        </button>
      </div>

      {flash && (
        <div className="banner banner--success" role="status" aria-live="polite">
          {flash}
        </div>
      )}
      {err && <BangLoi text={err} onRetry={doiDuLieu} />}

      {tab === "hang-cho" ? (
        <QueueTable
          rows={queue}
          scopeAll={scopeOf("san_xuat") === "all"}
          onOpen={(id) => setPreviewOrderId(id)}
          total={queueTotal}
          page={queuePage}
          onPage={setQueuePage}
        />
      ) : (
        <LenhTable
          rows={lenhs}
          ttFilter={ttFilter}
          onTtFilter={setTtFilter}
          q={q}
          onQ={setQ}
          orderFilter={orderFilter}
          onClearOrderFilter={() => setOrderFilter(null)}
          onOpen={(id) => setView({ mode: "detail", id })}
          onGoQueue={() => setTab("hang-cho")}
          tq={tq}
          // Bấm chấm là tới THẲNG chỗ sửa kèm mã lệnh — nhảy sang màn rồi còn phải tự tìm lệnh
          // trong 200 dòng thì vẫn là đổi màn, chỉ đỡ được nửa việc.
          onNhay={navigate ? (nhay, ma) => navigate(nhay.man, { focusLsxMa: ma }) : undefined}
          dem={demTheoTt}
          total={total}
          page={page}
          onPage={setPage}
        />
      )}

      {previewOrderId != null && (
        <LsxPreviewDrawer
          orderId={previewOrderId}
          canCreate={canCreate}
          onClose={() => setPreviewOrderId(null)}
          onCreated={sauKhiTao}
          onOpenLsx={(id) => {
            setPreviewOrderId(null);
            setView({ mode: "detail", id });
          }}
        />
      )}
    </main>
  );
}

// --- Tab 1: hàng chờ tiếp nhận ----------------------------------------------
function QueueTable({
  rows,
  scopeAll,
  onOpen,
  total,
  page,
  onPage,
}: {
  rows: HangChoItem[] | null;
  scopeAll: boolean;
  onOpen: (orderId: number) => void;
  /** TỔNG đơn chờ trên máy chủ (≠ `rows.length`, vốn chỉ là trang đang xem). */
  total: number;
  page: number;
  onPage: (p: number) => void;
}) {
  if (rows !== null && rows.length === 0) {
    return (
      <EmptyState
        icon="packageCheck"
        title={scopeAll ? "Không có đơn nào chờ lên lệnh." : "Bạn chỉ xem được lệnh của mình."}
        sub={
          scopeAll
            ? "Khi Sale bấm “Chuyển xuống sản xuất”, đơn hiện ở đây ngay — không cần tải lại trang."
            : "Hàng chờ tiếp nhận dành cho người có phạm vi toàn bộ (bộ phận Kế hoạch sản xuất)."
        }
      />
    );
  }
  return (
    <div className="khsx__tablewrap">
      <table className="khsx__table khsx__table--queue">
        <caption className="sr-only">Đơn hàng đã chuyển xuống sản xuất, chờ lên lệnh</caption>
        <thead>
          <tr>
            <th scope="col">Mã đơn</th>
            <th scope="col">Khách hàng</th>
            <th scope="col">Ngày giao</th>
            <th scope="col">Lên lệnh</th>
            <th scope="col" className="khsx__col--opt">Lưu ý sản xuất</th>
            <th scope="col" className="khsx__col--opt">Chuyển lúc</th>
            <th scope="col"><span className="sr-only">Mở</span></th>
          </tr>
        </thead>
        {rows === null ? (
          <Skeleton rows={4} cols={7} />
        ) : (
          <tbody>
            {rows.map((o) => {
              const pct = o.so_dong ? Math.round((o.so_dong_co_lsx / o.so_dong) * 100) : 0;
              return (
                <tr
                  key={o.order_id}
                  className={`khsx__row ${o.is_rush ? "khsx__row--rush" : ""}`}
                  role="button"
                  tabIndex={0}
                  aria-label={`Xem lệnh dự kiến của đơn ${o.order_no}`}
                  onClick={() => onOpen(o.order_id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onOpen(o.order_id);
                    }
                  }}
                >
                  <td>
                    <span className="khsx__code">{o.order_no}</span>
                    {o.is_rush && <ChipGap />}
                  </td>
                  <td>
                    {o.customer_name ?? "—"}
                    {o.sale_name && <div className="khsx__sub">{o.sale_name}</div>}
                  </td>
                  <td className={`khsx-num ${classHan(o.delivery_committed_date)}`}>
                    {ngay(o.delivery_committed_date)}
                  </td>
                  <td>
                    <div className="khsx-prog">
                      <b>
                        {o.so_dong_co_lsx}/{o.so_dong}
                      </b>
                      <span className="khsx-prog__bar">
                        <i style={{ width: `${pct}%` }} />
                      </span>
                    </div>
                  </td>
                  <td className="khsx__note khsx__col--opt" title={o.production_note ?? undefined}>
                    {o.production_note || "—"}
                  </td>
                  <td className="khsx-num khsx__col--opt">{ngayGio(o.san_xuat_released_at)}</td>
                  <td className="khsx__rowcta">
                    Xem lệnh dự kiến <Icon name="chevron" size={13} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        )}
      </table>
      <Pager total={total} page={page} size={SIZE_TRANG} onPage={onPage} unit="đơn chờ" />
    </div>
  );
}

// --- Tab 2: danh sách lệnh ---------------------------------------------------
function LenhTable({
  rows,
  ttFilter,
  onTtFilter,
  q,
  onQ,
  orderFilter,
  onClearOrderFilter,
  onOpen,
  onGoQueue,
  tq,
  onNhay,
  dem,
  total,
  page,
  onPage,
}: {
  rows: LsxListItem[] | null;
  ttFilter: string;
  onTtFilter: (k: string) => void;
  q: string;
  onQ: (v: string) => void;
  orderFilter: { id: number; code: string } | null;
  onClearOrderFilter: () => void;
  /** TỔNG lệnh khớp bộ lọc trên máy chủ. */
  total: number;
  page: number;
  onPage: (p: number) => void;
  onOpen: (id: number) => void;
  onGoQueue: () => void;
  /** Đèn theo lsx_id — tải RỜI sau bảng, nên thiếu khoá = chưa có tin, không phải "không sao". */
  tq: Record<number, LsxTongQuanOut["items"][number]>;
  onNhay?: (nhay: { man: string; id: number }, ma: string) => void;
  dem: (key: string) => number;
}) {
  const coLoc = ttFilter !== "all" || q.trim() !== "" || orderFilter != null;
  return (
    <>
      <div className="khsx__toolbar">
        <StatusTabs
          active={ttFilter}
          onChange={onTtFilter}
          tabs={TRANG_THAI_TABS.map((t) => ({ ...t, count: dem(t.key) }))}
        />
        <div className="khsx__spacer" />
        {orderFilter && (
          <span className="khsx__filterpill">
            Đơn {orderFilter.code}
            <button type="button" onClick={onClearOrderFilter} aria-label="Bỏ lọc theo đơn">
              <Icon name="x" size={12} />
            </button>
          </span>
        )}
        <label className="khsx__search">
          <Icon name="search" size={14} />
          <input
            value={q}
            onChange={(e) => onQ(e.target.value)}
            placeholder="Tìm mã lệnh / tên sản phẩm"
            aria-label="Tìm lệnh sản xuất"
          />
        </label>
      </div>

      {rows !== null && rows.length === 0 ? (
        coLoc ? (
          <EmptyState
            icon="search"
            title="Không tìm thấy lệnh khớp bộ lọc."
            action={
              <Button
                variant="secondary"
                onClick={() => {
                  onTtFilter("all");
                  onQ("");
                  onClearOrderFilter();
                }}
              >
                Xoá bộ lọc
              </Button>
            }
          />
        ) : (
          <EmptyState
            icon="clipboard"
            title="Chưa có lệnh sản xuất nào."
            sub="Lệnh sinh ra từ đơn Sale đã chuyển xuống sản xuất."
            action={
              <Button variant="secondary" onClick={onGoQueue}>
                Sang Hàng chờ →
              </Button>
            }
          />
        )
      ) : (
        <div className="khsx__tablewrap">
          <table className="khsx__table khsx__table--lenh">
            <caption className="sr-only">Danh sách lệnh sản xuất</caption>
            <thead>
              <tr>
                <th scope="col">Mã lệnh</th>
                <th scope="col">Sản phẩm</th>
                <th scope="col">Đơn · Khách</th>
                <th scope="col" className="khsx-th--num">SL</th>
                {/* Tiêu đề nói CHẶNG, không nói đơn vị: bảng liệt kê nhiều lệnh, lệnh sách có thể
                    đếm "TỜ CHẠY MÁY" còn lệnh bao bì đếm "TẤM" — một chữ ở đây không gánh nổi hai.
                    Đơn vị nằm trong từng ô, đọc từ `don_vi_to` server gửi kèm mỗi dòng. */}
                <th scope="col" className="khsx-th--num">Vào máy</th>
                <th scope="col" className="khsx-th--num">CĐ</th>
                <th scope="col" className="khsx__col--opt">Tổ đầu</th>
                <th scope="col">Hạn</th>
                <th scope="col">Vướng</th>
                <th scope="col">Trạng thái</th>
              </tr>
            </thead>
            {rows === null ? (
              <Skeleton rows={5} cols={10} />
            ) : (
              <tbody>
                {rows.map((l) => (
                  <tr
                    key={l.id}
                    className={`khsx__row ${l.is_rush ? "khsx__row--rush" : ""}`}
                    role="button"
                    tabIndex={0}
                    aria-label={`Mở lệnh ${l.ma}`}
                    onClick={() => onOpen(l.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onOpen(l.id);
                      }
                    }}
                  >
                    <td>
                      <span className="khsx__code">{l.ma}</span>
                      {l.is_rush && <ChipGap />}
                    </td>
                    {/* Lệnh chỉ mang tên bộ phận ("Bìa") → phải nói rõ nó thuộc sản phẩm thương
                        mại nào, không thì nhìn danh sách không biết bìa của cuốn nào. */}
                    <td className="khsx__name" title={l.nhom ? `${l.nhom} — ${l.ten}` : l.ten}>
                      {l.ten}
                      {l.nhom && <div className="khsx__sub khsx__sub--nhom">{l.nhom}</div>}
                    </td>
                    <td>
                      {l.order_no ?? "—"}
                      {l.customer_name && <div className="khsx__sub">{l.customer_name}</div>}
                    </td>
                    <td className="khsx-num">
                      {num(l.so_luong_dat)} <span className="khsx-unit">{l.don_vi_tinh}</span>
                    </td>
                    <td className="khsx-num">
                      {num(l.so_to_ke_hoach)}{" "}
                      <span className="khsx-unit">{nhanDonVi(l.don_vi_to)}</span>
                    </td>
                    <td className={`khsx-num ${l.so_cong_doan === 0 ? "khsx__bad" : ""}`}>
                      {l.so_cong_doan}
                    </td>
                    <td className="khsx__col--opt">{l.to_dau_ten ?? "—"}</td>
                    <td>
                      <div
                        className={`khsx-num ${classHanLich(tq[l.id]?.slack_ngay, l.han_hoan_thanh_sx)}`}
                        title={
                          tq[l.id]?.slack_ngay != null
                            ? tq[l.id]!.slack_ngay! < 0
                              ? `Lịch đang vượt hạn ${-tq[l.id]!.slack_ngay!} ngày làm việc`
                              : `Lịch còn dư ${tq[l.id]!.slack_ngay!} ngày làm việc`
                            : undefined
                        }
                      >
                        SX {ngay(l.han_hoan_thanh_sx)}
                      </div>
                      <div className="khsx__sub">Giao {ngay(l.han_giao_khach)}</div>
                    </td>
                    <td>
                      <DenTienDo
                        den={tq[l.id]?.den}
                        onNhay={onNhay ? (nhay) => onNhay(nhay, l.ma) : undefined}
                      />
                    </td>
                    <td>
                      <TrangThaiPill tt={l.trang_thai} />
                    </td>
                  </tr>
                ))}
              </tbody>
            )}
          </table>
        </div>
      )}

      {rows !== null && rows.length > 0 && (
        <Pager total={total} page={page} size={SIZE_TRANG} onPage={onPage} unit="lệnh" />
      )}
    </>
  );
}
