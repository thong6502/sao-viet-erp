// BÀN BÀI GHÉP (print gang) — controller master↔detail (điều hướng bằng state, không react-router).
//
// Gom công đoạn IN của nhiều LSX cùng giấy vào 1 tờ, chạy máy 1 lần. 2 khu:
//   • CÔNG ĐOẠN IN CHỜ XẾP — LSX sẵn sàng, cùng giấy, chưa ghép → tick nhiều → "Tạo bài ghép".
//   • DANH SÁCH BÀI GHÉP — mở chi tiết: kiểm tương thích · giấy/khổ chung · số tờ · sẵn sàng xếp lịch.
// Lát này DỪNG ở "sẵn sàng xếp lịch": chưa bình bài hình học, chưa xuất kẽm, chưa Gantt.
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  api,
  type BaiGhepListItem,
  type HangChoGhepItem,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { BaiGhepDetailView } from "./BaiGhepDetailView";
import { BangLoi, ChipGap, EmptyState, Skeleton, TrangThaiPill, classHan, ngay, num } from "./keHoachSxShared";
import "./ke-hoach-sx.css";
import "./bai-ghep.css";

type View = { mode: "list" } | { mode: "detail"; id: number };

export function BaiGhepPage({
  eventTick,
  onBadgeStale,
}: {
  eventTick?: number;
  onBadgeStale?: () => void;
}) {
  const { token } = useAuth();
  const can = useCan();
  const canCreate = can("san_xuat", "create");

  const [view, setView] = useState<View>({ mode: "list" });
  const [tab, setTab] = useState<"cho" | "list">("cho");
  const [pool, setPool] = useState<HangChoGhepItem[] | null>(null);
  const [list, setList] = useState<BaiGhepListItem[] | null>(null);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [q, setQ] = useState("");
  const [flash, setFlash] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const loadPool = useCallback(() => {
    if (!token) return;
    api.baiGhep
      .hangCho(token, { q: q.trim() || undefined })
      .then((r) => setPool(r.items))
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)));
  }, [token, q]);

  const loadList = useCallback(() => {
    if (!token) return;
    api.baiGhep
      .list(token)
      .then((r) => setList(r.items))
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)));
  }, [token]);

  useEffect(() => {
    const t = setTimeout(loadPool, q ? 250 : 0);
    return () => clearTimeout(t);
  }, [loadPool, eventTick, q]);
  useEffect(() => loadList(), [loadList, eventTick]);
  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), 5000);
    return () => clearTimeout(t);
  }, [flash]);

  function toggle(id: number) {
    setPicked((p) => {
      const n = new Set(p);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }

  async function taoBaiGhep() {
    if (!token || picked.size < 1) return;
    setCreating(true);
    setErr(null);
    try {
      const bg = await api.baiGhep.tao(token, [...picked]);
      setPicked(new Set());
      setFlash(`Đã tạo bài ghép ${bg.ma} · ${bg.thanh_vien.length} lệnh`);
      onBadgeStale?.();
      loadPool();
      loadList();
      setView({ mode: "detail", id: bg.id });
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  }

  const doiDuLieu = useCallback(() => {
    loadPool();
    loadList();
    onBadgeStale?.();
  }, [loadPool, loadList, onBadgeStale]);

  if (view.mode === "detail") {
    return (
      <main className="khsx bghep">
        <BaiGhepDetailView
          baiGhepId={view.id}
          onBack={() => setView({ mode: "list" })}
          onChanged={doiDuLieu}
        />
      </main>
    );
  }

  return (
    <main className="khsx bghep">
      <header className="khsx__head">
        <p className="eyebrow">Sản xuất</p>
        <div className="khsx__headrow">
          <h1 className="khsx__title">Bài ghép</h1>
          <span className="khsx__count">
            {num(pool?.length ?? 0)} lệnh chờ ghép · {num(list?.length ?? 0)} bài ghép
          </span>
        </div>
      </header>

      <div className="khsx__segrow" role="tablist" aria-label="Khu vực làm việc">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "cho"}
          className={`seg ${tab === "cho" ? "is-active" : ""}`}
          onClick={() => setTab("cho")}
        >
          Công đoạn in chờ xếp
          {(pool?.length ?? 0) > 0 && <span className="chip-count chip-count--alert">{pool?.length}</span>}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "list"}
          className={`seg ${tab === "list" ? "is-active" : ""}`}
          onClick={() => setTab("list")}
        >
          Bài ghép
          <span className="chip-count">{list?.length ?? 0}</span>
        </button>
      </div>

      {flash && (
        <div className="banner banner--success" role="status" aria-live="polite">
          {flash}
        </div>
      )}
      {err && <BangLoi text={err} onRetry={doiDuLieu} />}

      {tab === "cho" ? (
        <ChoTable
          rows={pool}
          picked={picked}
          onToggle={toggle}
          q={q}
          onQ={setQ}
          canCreate={canCreate}
          creating={creating}
          onTao={taoBaiGhep}
        />
      ) : (
        <BaiGhepTable rows={list} onOpen={(id) => setView({ mode: "detail", id })} onGoCho={() => setTab("cho")} />
      )}
    </main>
  );
}

// --- Khu 1: công đoạn in chờ xếp --------------------------------------------
function ChoTable({
  rows,
  picked,
  onToggle,
  q,
  onQ,
  canCreate,
  creating,
  onTao,
}: {
  rows: HangChoGhepItem[] | null;
  picked: Set<number>;
  onToggle: (id: number) => void;
  q: string;
  onQ: (v: string) => void;
  canCreate: boolean;
  creating: boolean;
  onTao: () => void;
}) {
  return (
    <>
      <div className="khsx__toolbar">
        <div className="khsx__search">
          <Icon name="search" size={15} />
          <input
            type="search"
            value={q}
            onChange={(e) => onQ(e.target.value)}
            placeholder="Tìm mã / tên lệnh…"
            aria-label="Tìm lệnh chờ ghép"
          />
        </div>
        <span className="khsx__spacer" />
        {picked.size > 0 && <span className="bghep-picked">{picked.size} lệnh đã chọn</span>}
        <Button
          variant="accent"
          disabled={!canCreate || picked.size < 1 || creating}
          loading={creating}
          onClick={onTao}
        >
          Tạo bài ghép{picked.size > 0 ? ` (${picked.size})` : ""}
        </Button>
      </div>

      <div className="khsx__tablewrap">
        <table className="khsx__table khsx__table--queue">
          <thead>
            <tr>
              <th className="bghep-check" aria-label="Chọn" />
              <th>Lệnh</th>
              <th>Giấy</th>
              <th className="khsx-num">Số màu</th>
              <th>Khổ TP</th>
              <th className="khsx-num">Số lượng</th>
              <th>Hạn in</th>
            </tr>
          </thead>
          {rows == null ? (
            <Skeleton rows={5} cols={7} />
          ) : rows.length === 0 ? (
            <tbody>
              <tr>
                <td colSpan={7}>
                  <EmptyState
                    icon="layers"
                    title="Không có lệnh nào chờ ghép"
                    sub="Lệnh sản xuất phải ở trạng thái 'sẵn sàng' và có công đoạn in mới hiện ở đây."
                  />
                </td>
              </tr>
            </tbody>
          ) : (
            <tbody>
              {rows.map((r) => {
                const on = picked.has(r.lsx_id);
                return (
                  <tr
                    key={r.lsx_id}
                    className={`khsx__row ${r.is_rush ? "khsx__row--rush" : ""} ${on ? "bghep-row--on" : ""}`}
                    onClick={() => onToggle(r.lsx_id)}
                  >
                    <td className="bghep-check">
                      <input
                        type="checkbox"
                        checked={on}
                        onChange={() => onToggle(r.lsx_id)}
                        onClick={(e) => e.stopPropagation()}
                        aria-label={`Chọn ${r.ma}`}
                      />
                    </td>
                    <td>
                      <div className="khsx__code">{r.ma}</div>
                      <div className="khsx__name">
                        {r.ten || "—"} {r.is_rush && <ChipGap />}
                      </div>
                      {r.customer_name && <div className="khsx__sub">{r.customer_name}</div>}
                    </td>
                    <td>
                      {r.giay_ten || "—"}
                      {r.gsm ? <span className="khsx-unit"> · {r.gsm} gsm</span> : null}
                    </td>
                    <td className="khsx-num">
                      {r.so_mau_a ?? 0}/{r.so_mau_b ?? 0}
                    </td>
                    <td>{r.kho_tp || "—"}</td>
                    <td className="khsx-num">
                      {num(r.so_luong_dat)} <span className="khsx-unit">{r.don_vi_tinh}</span>
                    </td>
                    <td className={classHan(r.han_hoan_thanh_sx)}>{ngay(r.han_hoan_thanh_sx)}</td>
                  </tr>
                );
              })}
            </tbody>
          )}
        </table>
      </div>
    </>
  );
}

// --- Khu 2: danh sách bài ghép ----------------------------------------------
function BaiGhepTable({
  rows,
  onOpen,
  onGoCho,
}: {
  rows: BaiGhepListItem[] | null;
  onOpen: (id: number) => void;
  onGoCho: () => void;
}) {
  return (
    <div className="khsx__tablewrap">
      <table className="khsx__table khsx__table--lenh">
        <thead>
          <tr>
            <th>Bài ghép</th>
            <th>Giấy · khổ in</th>
            <th className="khsx-num">Số tờ</th>
            <th>Hạn in gần nhất</th>
            <th>Trạng thái</th>
          </tr>
        </thead>
        {rows == null ? (
          <Skeleton rows={4} cols={5} />
        ) : rows.length === 0 ? (
          <tbody>
            <tr>
              <td colSpan={5}>
                <EmptyState
                  icon="layers"
                  title="Chưa có bài ghép"
                  sub="Chọn các lệnh cùng giấy ở 'Công đoạn in chờ xếp' rồi bấm Tạo bài ghép."
                  action={
                    <Button variant="secondary" onClick={onGoCho}>
                      Tới hàng chờ ghép
                    </Button>
                  }
                />
              </td>
            </tr>
          </tbody>
        ) : (
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.id}
                className="khsx__row"
                role="button"
                tabIndex={0}
                onClick={() => onOpen(r.id)}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onOpen(r.id))}
              >
                <td>
                  <div className="khsx__code">{r.ma}</div>
                  <div className="khsx__sub">{r.so_lsx} lệnh</div>
                </td>
                <td>
                  {r.giay_ten || <span className="khsx-muted">chưa chọn giấy</span>}
                  {r.kho_in && <span className="khsx-unit"> · {r.kho_in} mm</span>}
                </td>
                <td className="khsx-num">
                  {r.so_to_tot ? num(r.so_to_tot) : "—"}
                  {r.tong_to ? <span className="khsx-unit"> (+{num(r.tong_to - r.so_to_tot)} hao)</span> : null}
                </td>
                <td>{ngay(r.han_in_muon_nhat)}</td>
                <td>
                  <TrangThaiPill tt={r.trang_thai} />
                  {r.so_canh_bao > 0 && (
                    <span className="khsx-warn-inline" title="Có cảnh báo mềm">
                      <Icon name="help" size={11} /> {r.so_canh_bao}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        )}
      </table>
    </div>
  );
}
