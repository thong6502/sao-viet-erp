// Hộp việc của 1 TỔ khối Sản xuất (Lát 1) — bấm 1 tổ dưới section "Sản xuất" trên navbar.
// 2 TẦNG THEO QUYỀN (backend tự chọn view): tổ trưởng/giám sát thấy FULL lệnh đang chạy ghé tổ
// + mở drawer để GÁN thợ vào từng công đoạn của tổ mình; thợ CHỈ xem lệnh mình được gán (read-only).
// Realtime: badge việc + toast do AppShell (kênh SSE chung) đẩy; ở đây refetch theo `refetchSignal`.
// Tái dùng hệ thiết kế đen/kem/cam: scaffold .lsx-tolenh / .lsx-rcards / .lsx-badge + drawer .rc-drawer.
// ① Card có dải footer kế hoạch (chạy·máy in·khuôn). ② Toggle Danh sách↔Lịch (gom theo độ khẩn).
// ③ Drawer: chip kế hoạch read-only + xếp MÁY finishing + CA cho bước tổ mình (1.12, record-only).
import { Fragment, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, api } from "../api/client";
import type { ToInboxItem, ToInboxOut, ToInboxStep, StepChoNhan, ToMember, FinishingMay } from "../api/client";
import { ToastStack, useToasts } from "./LsxToast";
import { hanGiao, fmtDate } from "../utils/format";
import "./lenh-san-xuat.css";
import "./rebuild-catalog.css";

const maLenh = (id: number) => `LSX-${String(id).padStart(4, "0")}`;
const fmtNum = (n: number) => n.toLocaleString("vi-VN");
const CA_OPTS = ["Ca 1", "Ca 2", "Ca 3"] as const;

// Ngày hiệu lực để xếp cụm Lịch: hạn nội bộ → ngày chạy → hạn khách.
const effDue = (it: ToInboxItem): string | null =>
  it.han_giao_noi_bo ?? it.ngay_chay ?? it.han_giao_khach;

type Bucket = "over" | "today" | "week" | "later";
const dueBucket = (iso: string | null): Bucket => {
  if (!iso) return "later";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "later";
  const today = new Date();
  const diff = Math.round(
    (Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) -
      Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())) / 86400000,
  );
  if (diff < 0) return "over";
  if (diff === 0) return "today";
  if (diff <= 7) return "week";
  return "later";
};
const LICH_GROUPS: { key: Bucket; label: string }[] = [
  { key: "over", label: "Quá hạn" },
  { key: "today", label: "Hôm nay" },
  { key: "week", label: "Tuần này" },
  { key: "later", label: "Sau" },
];

// --- Icon (stroke 1.7, currentColor — đồng bộ module) ---
const IcUsers = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" />
    <path d="M22 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" />
  </svg>
);
const IcInbox = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M22 12h-6l-2 3h-4l-2-3H2" /><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11Z" />
  </svg>
);
const IcCrown = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M11.56 3.69a.5.5 0 0 1 .88 0l2.54 4.6 4.9-2.2a.5.5 0 0 1 .7.58l-2.02 8.02a1 1 0 0 1-.97.76H6.4a1 1 0 0 1-.97-.76L3.42 6.67a.5.5 0 0 1 .7-.58l4.9 2.2 2.54-4.6Z" /><path d="M6 19h12" />
  </svg>
);
const IcHat = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M2 18h20" /><path d="M10 10V5a2 2 0 0 1 4 0v5" /><path d="M4 18a8 8 0 0 1 16 0" />
  </svg>
);
const IcChevron = () => (
  <svg className="lsx-chev" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg>
);
const IcPlus = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
);
const IcX = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
);
const IcAlert = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16h.01" /></svg>
);
const IcClock = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></svg>
);
const IcFlag = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" /><path d="M4 22v-7" /></svg>
);
const IcNote = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15.5 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L15.5 3Z" /><path d="M15 3v5h5M8.5 12.5h7M8.5 16h5" /></svg>
);
const IcSpec = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="8" width="18" height="8" rx="1.5" /><path d="M7 8v3M11 8v4M15 8v3M19 8v4" /></svg>
);
// Lịch (calendar) — footer card + toggle + cụm lịch.
const IcCalendar = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="4.5" width="18" height="17" rx="2" /><path d="M3 9.5h18M8 2.5v4M16 2.5v4" /></svg>
);
// Máy in (printer) — nhãn máy in read-only.
const IcPrinter = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9V3h12v6" /><path d="M6 18H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-1" /><rect x="7" y="14.5" width="10" height="6.5" rx="1" /><path d="M17.5 12h.01" /></svg>
);
// Khuôn bế (stamp / con dấu) — nhãn khuôn read-only.
const IcStamp = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 22h14" /><path d="M19.27 13.73A2.5 2.5 0 0 0 17.5 13h-11A2.5 2.5 0 0 0 4 15.5V17a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-1.5c0-.66-.26-1.3-.73-1.77Z" /><path d="M14 13V8.5C14 7 15 7 15 5a3 3 0 0 0-6 0c0 2 1 2 1 3.5V13" /></svg>
);
// Máy finishing (settings-2) — nhãn ô chọn máy bế/cán.
const IcCog = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 7h-9M14 17H5" /><circle cx="17" cy="17" r="3" /><circle cx="7" cy="7" r="3" /></svg>
);
// List (toggle Danh sách).
const IcList = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" /></svg>
);
// Info (i) — dòng "máy chỉ ghi nhận".
const IcInfo = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 16v-4M12 8h.01" /></svg>
);
// Check — số đạt + nút Ghi/Xác nhận (Lát 2).
const IcCheck = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg>
);
// Package (hộp) — bàn giao 2 chiều (Lát 2).
const IcPackage = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m7.5 4.27 9 5.15" /><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" /><path d="m3.3 7 8.7 5 8.7-5" /><path d="M12 22V12" /></svg>
);

export function ToSanXuatView({
  toId, ten, ma, token, refetchSignal,
}: { toId: number; ten: string; ma?: string; token: string; refetchSignal: number }) {
  const [data, setData] = useState<ToInboxOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [mode, setMode] = useState<"list" | "lich">("list");        // danh sách ↔ lịch
  const [openId, setOpenId] = useState<number | null>(null);          // lệnh đang mở drawer
  const [members, setMembers] = useState<ToMember[] | null>(null);    // thợ của tổ (lazy)
  const [machines, setMachines] = useState<FinishingMay[] | null>(null);  // máy finishing (lazy; BE đã lọc non-press)
  const [pickerStep, setPickerStep] = useState<number | null>(null);  // bước đang mở picker gán
  const [pickerSel, setPickerSel] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const toasts = useToasts();

  const load = useCallback(async () => {
    setErr(null);
    try {
      const d = await api.lenhSanXuat.toInbox(token, toId);
      setData(d);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Không tải được hộp việc của tổ.");
    } finally {
      setLoading(false);
    }
  }, [token, toId]);

  useEffect(() => { setLoading(true); load(); }, [load, refetchSignal]);

  // Nạp danh sách thợ của tổ khi mở drawer (chỉ khi được phép gán). Reset khi đổi tổ (component re-key).
  useEffect(() => {
    if (openId !== null && data?.can_assign && members === null) {
      api.lenhSanXuat.toMembers(token, toId).then((r) => setMembers(r.items)).catch(() => setMembers([]));
    }
  }, [openId, data, members, token, toId]);

  // Nạp danh mục MÁY finishing (bế/cán/bồi) khi mở drawer + được phép xếp. Endpoint gác san_xuat:read
  // (tổ trưởng có) + đã lọc non-press SERVER-SIDE — dùng thẳng items, không lọc FE.
  useEffect(() => {
    if (openId !== null && data?.can_assign && machines === null) {
      api.lenhSanXuat.finishingMays(token)
        .then((r) => setMachines(r.items))
        .catch(() => setMachines([]));
    }
  }, [openId, data, machines, token]);

  const openItem = useMemo(
    () => (openId === null ? null : data?.items.find((i) => i.lenh_id === openId) ?? null),
    [openId, data],
  );

  const closeDrawer = useCallback(() => {
    setOpenId(null); setPickerStep(null); setPickerSel(new Set());
  }, []);

  const doAssign = useCallback(async (stepId: number, userIds: number[]) => {
    if (userIds.length === 0) return;
    setBusy(true);
    try {
      await api.lenhSanXuat.assign(token, stepId, userIds);
      toasts.ok(`Đã gán ${userIds.length} thợ vào công đoạn`);
      setPickerStep(null); setPickerSel(new Set());
      await load();
    } catch (e) {
      toasts.err(e instanceof ApiError ? e.message : "Không gán được thợ.");
    } finally {
      setBusy(false);
    }
  }, [token, load, toasts]);

  const doUnassign = useCallback(async (stepId: number, userId: number, ten: string) => {
    setBusy(true);
    try {
      await api.lenhSanXuat.unassign(token, stepId, userId);
      toasts.ok(`Đã bỏ gán ${ten}`);
      await load();
    } catch (e) {
      toasts.err(e instanceof ApiError ? e.message : "Không bỏ gán được.");
    } finally {
      setBusy(false);
    }
  }, [token, load, toasts]);

  // 1.12 — xếp MÁY finishing + CA cho 1 bước (record-only). Gửi CẢ 2 giá trị hiện tại.
  const doSetMayCa = useCallback(async (stepId: number, may_id: number | null, ca: string | null) => {
    setBusy(true);
    try {
      await api.lenhSanXuat.setStepMayCa(token, stepId, { may_id, ca });
      toasts.ok("Đã lưu máy/ca");
      await load();
    } catch (e) {
      toasts.err(e instanceof ApiError ? e.message : "Không lưu được máy/ca.");
    } finally {
      setBusy(false);
    }
  }, [token, load, toasts]);

  // Lát 2 — ghi 1 đợt sản lượng (record-only, cộng dồn). Trả boolean để card CLEAR ô nhập khi ghi xong.
  const doGhiSanLuong = useCallback(async (
    stepId: number, body: { so_dat: number; so_hong: number; don_vi: string },
  ): Promise<boolean> => {
    setBusy(true);
    try {
      await api.lenhSanXuat.ghiSanLuong(token, stepId, body);
      toasts.ok("Đã ghi sản lượng");
      await load();
      return true;
    } catch (e) {
      toasts.err(e instanceof ApiError ? e.message : "Không ghi được sản lượng.");
      return false;
    } finally {
      setBusy(false);
    }
  }, [token, load, toasts]);

  // Lát 2 — giao số sang bước kế (backend ting đích danh tổ nhận). toTenNext chỉ để hiển thị toast.
  const doBanGiao = useCallback(async (
    stepId: number, body: { so_giao: number; don_vi: string }, toTenNext: string,
  ) => {
    setBusy(true);
    try {
      await api.lenhSanXuat.banGiao(token, stepId, body);
      toasts.ok(`Đã giao sang ${toTenNext}`);
      await load();
    } catch (e) {
      toasts.err(e instanceof ApiError ? e.message : "Không giao được.");
    } finally {
      setBusy(false);
    }
  }, [token, load, toasts]);

  // Lát 2 — tổ nhận xác nhận số thực nhận (lệch được, kèm lý do). Sau khi nhận, cho_nhan biến mất (BE) → khối C tự ẩn.
  const doXacNhanNhan = useCallback(async (
    banGiaoId: number, body: { so_nhan: number; ly_do_lech?: string | null },
  ) => {
    setBusy(true);
    try {
      await api.lenhSanXuat.xacNhanNhan(token, banGiaoId, body);
      toasts.ok("Đã xác nhận nhận");
      await load();
    } catch (e) {
      toasts.err(e instanceof ApiError ? e.message : "Không xác nhận được.");
    } finally {
      setBusy(false);
    }
  }, [token, load, toasts]);

  const count = data?.items.length ?? 0;
  const canAssign = !!data?.can_assign;
  const isFull = data?.view === "full";
  const showBody = !loading && !err && count > 0;

  return (
    <main className="lsx">
      <header className="lsx-head">
        <div className="lsx-head__lead">
          <div className="lsx-eyebrow"><IcUsers /> Hộp việc tổ</div>
          <div className="lsx-head__titlerow">
            <h1 className="lsx-head__title">{ten}</h1>
            {ma && <span className="lsx-code">{ma}</span>}
          </div>
          <p className="lsx-head__sub">
            {isFull
              ? "Toàn bộ lệnh đang chạy ghé tổ — bấm 1 lệnh để gán thợ vào công đoạn."
              : "Việc được giao cho bạn — bấm để xem chi tiết công đoạn."}
          </p>
        </div>
        <div className="lsx-head__actions">
          {showBody && (
            <div className="lsx-seg" role="tablist" aria-label="Chế độ xem">
              <button type="button" role="tab" aria-selected={mode === "list"}
                className={`lsx-seg__btn ${mode === "list" ? "is-on" : ""}`} onClick={() => setMode("list")}>
                <IcList /> Danh sách
              </button>
              <button type="button" role="tab" aria-selected={mode === "lich"}
                className={`lsx-seg__btn ${mode === "lich" ? "is-on" : ""}`} onClick={() => setMode("lich")}>
                <IcCalendar /> Lịch
              </button>
            </div>
          )}
          <span className="lsx-rolechip">
            {canAssign ? <IcCrown /> : <IcHat />}
            {canAssign ? "Tổ trưởng" : isFull ? "Giám sát" : "Thợ"}
          </span>
          <span className={`lsx-count lsx-count--lg ${count > 0 ? "lsx-count--hot" : "lsx-count--idle"}`}>
            <IcInbox /> {count} việc
          </span>
        </div>
      </header>

      {loading ? (
        <div className="lsx-tolenh" aria-busy="true">
          {[0, 1, 2].map((i) => <div key={i} className="lsx-skel" />)}
        </div>
      ) : err ? (
        <div className="lsx-soon">
          <span className="lsx-soon__ic" style={{ color: "var(--rust)" }}><IcAlert /></span>
          <h2 className="lsx-soon__title">Lỗi tải hộp việc</h2>
          <p className="lsx-soon__sub">{err}</p>
          <button type="button" className="btn btn--primary" style={{ marginTop: 12 }} onClick={() => { setLoading(true); load(); }}>
            Thử lại
          </button>
        </div>
      ) : count === 0 ? (
        <div className="lsx-soon">
          <span className="lsx-soon__ic"><IcInbox /></span>
          <h2 className="lsx-soon__title">{isFull ? "Chưa có lệnh nào ở tổ" : "Chưa được giao việc"}</h2>
          <p className="lsx-soon__sub">
            {isFull
              ? "Khi kế hoạch PHÁT lệnh có công đoạn của tổ, việc sẽ hiện ở đây kèm thông báo."
              : "Tổ trưởng gán việc cho bạn thì việc sẽ hiện ở đây kèm thông báo."}
          </p>
        </div>
      ) : mode === "list" ? (
        <ul className="lsx-tolenh">
          {data!.items.map((it) => (
            <li key={it.lenh_id}>
              <LenhCard item={it} onOpen={() => setOpenId(it.lenh_id)} />
            </li>
          ))}
        </ul>
      ) : (
        <LichView items={data!.items} onOpen={setOpenId} />
      )}

      {openItem && data && (
        <LenhDrawer
          item={openItem}
          toTen={ten}
          canAssign={canAssign}
          members={members}
          machines={machines}
          pickerStep={pickerStep}
          pickerSel={pickerSel}
          busy={busy}
          onClose={closeDrawer}
          onOpenPicker={(sid) => { setPickerStep(sid); setPickerSel(new Set()); }}
          onTogglePick={(uid) => setPickerSel((s) => { const n = new Set(s); if (n.has(uid)) n.delete(uid); else n.add(uid); return n; })}
          onConfirmPick={(sid) => doAssign(sid, [...pickerSel])}
          onUnassign={doUnassign}
          onSetMayCa={doSetMayCa}
          onGhiSanLuong={doGhiSanLuong}
          onBanGiao={doBanGiao}
          onXacNhanNhan={doXacNhanNhan}
        />
      )}

      <ToastStack toasts={toasts.toasts} onDismiss={toasts.dismiss} />
    </main>
  );
}

// --- 1 lệnh-card (tầng danh sách) — hàng chính + dải footer kế hoạch (chạy·máy in·khuôn) ---
function LenhCard({ item, onOpen }: { item: ToInboxItem; onOpen: () => void }) {
  const mySteps = item.steps.filter((s) => s.is_mine);
  const meta: { ic: ReactNode; node: ReactNode }[] = [];
  if (item.ngay_chay) meta.push({ ic: <IcCalendar />, node: `Chạy ${fmtDate(item.ngay_chay)}` });
  if (item.may_in_label) meta.push({ ic: <IcPrinter />, node: item.may_in_label });
  if (item.khuon_be_label) meta.push({ ic: <IcStamp />, node: item.khuon_be_label });

  return (
    <button type="button" className="lsx-tolenh__card" onClick={onOpen}>
      <div className="lsx-tolenh__main">
        <div className="lsx-tolenh__lead">
          <div className="lsx-tolenh__idline">
            <span className="lsx-code">{maLenh(item.lenh_id)}</span>
            {item.muc_tieu_sl > 0 && (
              <span className="lsx-badge lsx-badge--neutral"><b className="num">{fmtNum(item.muc_tieu_sl)}</b>&nbsp;cái</span>
            )}
          </div>
          <div className="lsx-tolenh__ap">{item.order_no ? `Đơn ${item.order_no}` : `Lệnh #${item.lenh_id}`}</div>
          {item.khach && <div className="lsx-tolenh__cust">{item.khach}</div>}
        </div>
        <div className="lsx-tolenh__mid">
          {mySteps.map((s) => (
            <div className="lsx-tolenh__steprow" key={s.step_id}>
              <span className="lsx-tolenh__steplbl">CĐ{s.thu_tu}</span>
              <span className="lsx-tolenh__stepten">{s.ten}</span>
              {s.assignees.length > 0 ? (
                <span className="lsx-who">
                  {s.assignees.slice(0, 3).map((a) => (
                    <span key={a.user_id} className="lsx-badge lsx-badge--neutral">{a.ten}</span>
                  ))}
                  {s.assignees.length > 3 && <span className="lsx-tolenh__num">+{s.assignees.length - 3}</span>}
                </span>
              ) : (
                <span className="lsx-badge lsx-badge--wait"><span className="lsx-badge__d" />Chưa gán thợ</span>
              )}
            </div>
          ))}
        </div>
        {(() => {
          const nb = hanGiao(item.han_giao_noi_bo ?? item.han_giao_khach);
          const showKH = !!item.han_giao_noi_bo && !!item.han_giao_khach;
          if (!nb) return null;
          return (
            <div className="lsx-duestack lsx-duestack--end lsx-tolenh__due">
              <span className={`lsx-due lsx-due--${nb.level}`}><IcClock /> {nb.label}</span>
              {showKH && <span className="lsx-hardline"><IcFlag /> Khách <b>{fmtDate(item.han_giao_khach)}</b></span>}
            </div>
          );
        })()}
        <IcChevron />
      </div>
      {meta.length > 0 && (
        <div className="lsx-tolenh__meta">
          {meta.map((m, i) => (
            <Fragment key={i}>
              {i > 0 && <span className="lsx-metadot" aria-hidden="true">·</span>}
              <span className="lsx-metaitem">{m.ic}<span>{m.node}</span></span>
            </Fragment>
          ))}
        </div>
      )}
    </button>
  );
}

// --- Chế độ LỊCH: gom lệnh theo cụm độ khẩn (ngày hiệu lực vs hôm nay), dòng rút gọn ---
function LichView({ items, onOpen }: { items: ToInboxItem[]; onOpen: (id: number) => void }) {
  return (
    <div className="lsx-lichwrap">
      {LICH_GROUPS.map((g) => {
        const rows = items.filter((it) => dueBucket(effDue(it)) === g.key);
        if (rows.length === 0) return null;
        const gIc = g.key === "over" ? <IcAlert /> : g.key === "today" ? <IcClock /> : <IcCalendar />;
        return (
          <section key={g.key} className="lsx-lichgroup">
            <div className={`lsx-lichgroup__hd lsx-lichgroup__hd--${g.key}`}>
              {gIc}
              <span className="lsx-lichgroup__name">{g.label}</span>
              <span className="lsx-lichgroup__n">{rows.length}</span>
            </div>
            <ul className="lsx-lichgroup__list">
              {rows.map((it) => {
                const due = hanGiao(effDue(it));
                return (
                  <li key={it.lenh_id}>
                    <button type="button" className="lsx-lrow" onClick={() => onOpen(it.lenh_id)}>
                      <span className="lsx-code">{maLenh(it.lenh_id)}</span>
                      <span className="lsx-lrow__ap">
                        {it.order_no ? `Đơn ${it.order_no}` : `Lệnh #${it.lenh_id}`}{it.khach ? ` · ${it.khach}` : ""}
                      </span>
                      {it.may_in_label && <span className="lsx-lrow__may"><IcPrinter /> {it.may_in_label}</span>}
                      {due && <span className={`lsx-due lsx-due--${due.level}`}><IcClock /> {due.label}</span>}
                      <IcChevron />
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

// --- Drawer chi tiết 1 lệnh: chip kế hoạch + routing traveler + gán thợ + xếp máy/ca per bước tổ mình ---
function LenhDrawer({
  item, toTen, canAssign, members, machines, pickerStep, pickerSel, busy,
  onClose, onOpenPicker, onTogglePick, onConfirmPick, onUnassign, onSetMayCa,
  onGhiSanLuong, onBanGiao, onXacNhanNhan,
}: {
  item: ToInboxItem; toTen: string; canAssign: boolean; members: ToMember[] | null; machines: FinishingMay[] | null;
  pickerStep: number | null; pickerSel: Set<number>; busy: boolean;
  onClose: () => void; onOpenPicker: (stepId: number) => void; onTogglePick: (uid: number) => void;
  onConfirmPick: (stepId: number) => void; onUnassign: (stepId: number, uid: number, ten: string) => void;
  onSetMayCa: (stepId: number, mayId: number | null, ca: string | null) => void;
  onGhiSanLuong: (stepId: number, body: { so_dat: number; so_hong: number; don_vi: string }) => Promise<boolean>;
  onBanGiao: (stepId: number, body: { so_giao: number; don_vi: string }, toTenNext: string) => void;
  onXacNhanNhan: (banGiaoId: number, body: { so_nhan: number; ly_do_lech?: string | null }) => void;
}) {
  // Esc để đóng.
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  const hasPlan = !!(item.ngay_chay || item.may_in_label || item.khuon_be_label);

  return (
    <div className="rc-drawer__scrim" role="dialog" aria-modal="true" aria-label={`Chi tiết ${maLenh(item.lenh_id)}`} onClick={onClose}>
      <aside className="rc-drawer" onClick={(e) => e.stopPropagation()}>
        <div className="rc-drawer__head">
          <div className="rc-drawer__kicker">Hộp việc · {toTen}</div>
          <div className="rc-drawer__title">{maLenh(item.lenh_id)}</div>
          <button type="button" className="rc-drawer__x" aria-label="Đóng" onClick={onClose}><IcX /></button>
        </div>
        <div className="rc-drawer__body">
          <div className="lsx-irow">
            <span>{item.order_no ? `Đơn ${item.order_no}` : `Lệnh #${item.lenh_id}`}{item.khach ? ` · ${item.khach}` : ""}</span>
            {item.muc_tieu_sl > 0 && <span className="strong">{fmtNum(item.muc_tieu_sl)} cái</span>}
          </div>

          {item.ghi_chu_ky_thuat && (
            <div className="lsx-dw__note" style={{ marginTop: 8 }}>
              <IcNote /><span><strong>Kỹ thuật:</strong> {item.ghi_chu_ky_thuat}</span>
            </div>
          )}

          {hasPlan && (
            <div className="lsx-planrow">
              {item.ngay_chay && <span className="lsx-planchip"><IcCalendar /> Chạy in <b>{fmtDate(item.ngay_chay)}</b></span>}
              {item.may_in_label && <span className="lsx-planchip"><IcPrinter /> {item.may_in_label}</span>}
              {item.khuon_be_label && <span className="lsx-planchip"><IcStamp /> Khuôn <b>{item.khuon_be_label}</b></span>}
            </div>
          )}

          {canAssign && (
            <p className="lsx-panel__hint" style={{ marginTop: 4 }}>
              Công đoạn <b>của tổ</b> (viền cam) gán thợ + xếp máy/ca được — thợ được gán sẽ thấy việc + nhận thông báo. Bước tổ khác chỉ xem.
            </p>
          )}

          <ul className="lsx-rcards" style={{ marginTop: 10 }}>
            {item.steps.map((s) => {
              const mineAssignable = canAssign && s.is_mine;
              const already = new Set(s.assignees.map((a) => a.user_id));
              const pool = (members ?? []).filter((m) => !already.has(m.user_id));
              const roMayCa = [s.may_label, s.ca].filter(Boolean).join(" · ");
              return (
                <li key={s.step_id} className={`lsx-rcard ${s.is_mine ? "is-mine" : ""}`}>
                  <div className="lsx-rcard__head">
                    <span className="lsx-rcard__no">{s.thu_tu}</span>
                    {s.is_mine && <span className="lsx-rcard__mine">Tổ mình</span>}
                  </div>
                  <div className="lsx-rcard__ten">{s.ten}</div>
                  {s.quy_cach && <div className="lsx-qc"><IcSpec /> {s.quy_cach}</div>}
                  <div className="lsx-rcard__to"><IcUsers /> {s.to_ten ?? "—"}</div>

                  {s.assignees.length > 0 ? (
                    <div className="lsx-who">
                      {s.assignees.map((a) => (
                        <span key={a.user_id} className="lsx-badge lsx-badge--neutral">
                          {a.ten}
                          {mineAssignable && (
                            <button type="button" className="lsx-chipx" disabled={busy}
                              aria-label={`Bỏ gán ${a.ten}`} onClick={() => onUnassign(s.step_id, a.user_id, a.ten)}>×</button>
                          )}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div className="lsx-rcard__wait"><IcAlert /> Chưa gán thợ</div>
                  )}

                  {mineAssignable && pickerStep !== s.step_id && (
                    <button type="button" className="lsx-addbtn" onClick={() => onOpenPicker(s.step_id)}>
                      <IcPlus /> Thêm thợ
                    </button>
                  )}

                  {mineAssignable && pickerStep === s.step_id && (
                    <div className="lsx-picker">
                      {members === null ? (
                        <div className="lsx-picker__row" aria-busy="true">Đang tải danh sách thợ…</div>
                      ) : pool.length === 0 ? (
                        <div className="lsx-picker__row">Không còn thợ nào trong tổ để gán.</div>
                      ) : (
                        pool.map((m) => (
                          <label key={m.user_id} className="lsx-picker__row">
                            <input type="checkbox" checked={pickerSel.has(m.user_id)} onChange={() => onTogglePick(m.user_id)} />
                            <span className="lsx-picker__name">{m.ten}</span>
                            {m.chuc_vu && <span className="lsx-picker__cv">{m.chuc_vu}</span>}
                          </label>
                        ))
                      )}
                      <div className="lsx-picker__foot">
                        <button type="button" className="btn btn--primary" disabled={busy || pickerSel.size === 0}
                          onClick={() => onConfirmPick(s.step_id)}>
                          {busy ? "Đang gán…" : `Gán ${pickerSel.size > 0 ? `(${pickerSel.size})` : ""}`}
                        </button>
                        <button type="button" className="btn btn--ghost" onClick={() => onOpenPicker(-1)}>Hủy</button>
                      </div>
                    </div>
                  )}

                  {mineAssignable ? (
                    <div className="lsx-mayca">
                      <div className="lsx-mayca__field">
                        <label className="lsx-mayca__lbl" htmlFor={`may-${s.step_id}`}>Máy bế / cán</label>
                        <div className="lsx-mayca__selwrap">
                          <IcCog />
                          <select id={`may-${s.step_id}`} className="lsx-mayca__sel"
                            value={s.may_id ?? ""} disabled={busy || machines === null}
                            onChange={(e) => onSetMayCa(s.step_id, e.target.value === "" ? null : Number(e.target.value), s.ca)}>
                            <option value="">— Chưa chọn —</option>
                            {(machines ?? []).map((m) => <option key={m.id} value={m.id}>{m.ten}</option>)}
                            {s.may_id != null && !(machines ?? []).some((m) => m.id === s.may_id) && (
                              <option value={s.may_id}>{s.may_label ?? `Máy #${s.may_id}`}</option>
                            )}
                          </select>
                        </div>
                      </div>
                      <div className="lsx-mayca__field">
                        <span className="lsx-mayca__lbl" id={`ca-${s.step_id}`}>Ca</span>
                        <div className="lsx-caseg" role="group" aria-labelledby={`ca-${s.step_id}`}>
                          {CA_OPTS.map((c) => {
                            const on = s.ca === c;
                            return (
                              <button key={c} type="button" className={`lsx-caseg__btn ${on ? "is-on" : ""}`}
                                aria-pressed={on} disabled={busy}
                                onClick={() => onSetMayCa(s.step_id, s.may_id, on ? null : c)}>
                                {c}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                      <p className="lsx-mayca__hint"><IcInfo /> Máy chỉ ghi nhận — không chặn phát</p>
                    </div>
                  ) : roMayCa ? (
                    <div className="lsx-rcard__mayca"><IcCog /> {roMayCa}</div>
                  ) : null}

                  {/* Lát 2 — sản lượng ghi nhận + bàn giao 2 chiều. Tổ mình: nhập + giao (+ nhận nếu có hàng đến).
                      Bước tổ khác/thợ: 1 dòng read-only tóm tắt. */}
                  {mineAssignable ? (
                    <>
                      <SanLuongGiao s={s} item={item} busy={busy}
                        onGhiSanLuong={onGhiSanLuong} onBanGiao={onBanGiao} />
                      {s.cho_nhan && (
                        <NhanBlock key={s.cho_nhan.ban_giao_id} choNhan={s.cho_nhan} busy={busy}
                          onXacNhanNhan={onXacNhanNhan} />
                      )}
                    </>
                  ) : (s.san_luong || s.da_giao > 0 || s.cho_nhan) ? (
                    <div className="lsx-ro2">
                      {s.san_luong && (
                        <span><IcCheck /> Đạt {fmtNum(s.san_luong.so_dat)} · Hỏng {fmtNum(s.san_luong.so_hong)}</span>
                      )}
                      {s.da_giao > 0 && <span><IcPackage /> đã giao {fmtNum(s.da_giao)}</span>}
                      {s.cho_nhan && <span>chờ nhận {fmtNum(s.cho_nhan.so_giao)}</span>}
                    </div>
                  ) : null}

                  {s.ghi_chu && <div className="lsx-stepnote"><IcNote /> {s.ghi_chu}</div>}
                </li>
              );
            })}
          </ul>
        </div>
      </aside>
    </div>
  );
}

// --- Lát 2 · SẢN LƯỢNG (record-only, cộng dồn) + BÀN GIAO sang bước kế ---
// State cục bộ per-bước: ô Đạt/Hỏng + đơn vị (đợt mới, clear sau khi ghi); ô số giao (rỗng = giao thẳng Σ đạt).
// Đơn vị mặc định theo lần ghi trước (nếu có), không thì "to". Component giữ mount qua load() nên input không tự reset —
// riêng ô Đạt/Hỏng clear TAY khi ghi thành công; ô giao để rỗng nên luôn bám Σ đạt mới nhất (placeholder), chống stale.
function SanLuongGiao({
  s, item, busy, onGhiSanLuong, onBanGiao,
}: {
  s: ToInboxStep; item: ToInboxItem; busy: boolean;
  onGhiSanLuong: (stepId: number, body: { so_dat: number; so_hong: number; don_vi: string }) => Promise<boolean>;
  onBanGiao: (stepId: number, body: { so_giao: number; don_vi: string }, toTenNext: string) => void;
}) {
  const [dat, setDat] = useState("");
  const [hong, setHong] = useState("");
  const [donVi, setDonVi] = useState<"to" | "con">(() => (s.san_luong?.don_vi === "con" ? "con" : "to"));
  const [giao, setGiao] = useState("");

  const digits = (v: string) => v.replace(/[^\d]/g, "");
  const unitLbl = (u: string) => (u === "con" ? "con" : "tờ");
  const soDat = s.san_luong?.so_dat ?? 0;
  const target = item.muc_tieu_sl;
  const thieu = target > 0 ? Math.max(0, target - soDat) : 0;
  // Bước KẾ = thứ tự lớn hơn, nhỏ nhất → tổ nhận.
  const next = item.steps.filter((x) => x.thu_tu > s.thu_tu).sort((a, b) => a.thu_tu - b.thu_tu)[0] ?? null;

  const submitSL = async () => {
    const d = Number(dat || "0");
    const h = Number(hong || "0");
    if (d <= 0 && h <= 0) return;
    const ok = await onGhiSanLuong(s.step_id, { so_dat: d, so_hong: h, don_vi: donVi });
    if (ok) { setDat(""); setHong(""); }
  };

  const giaoNum = giao.trim() === "" ? soDat : Number(giao);
  const submitBG = () => {
    if (!next || giaoNum <= 0) return;
    onBanGiao(s.step_id, { so_giao: giaoNum, don_vi: s.san_luong?.don_vi ?? donVi }, next.to_ten ?? `CĐ${next.thu_tu}`);
  };

  return (
    <div className="lsx-sl">
      {s.san_luong && (
        <div className="lsx-sl__done">
          <span className="lsx-sl__ok"><IcCheck /> Đạt <b>{fmtNum(s.san_luong.so_dat)}</b></span>
          <span className="lsx-sl__bad">✗ Hỏng <b>{fmtNum(s.san_luong.so_hong)}</b></span>
          <span className="lsx-sl__unit">{unitLbl(s.san_luong.don_vi)}</span>
          {target > 0 && (thieu > 0
            ? <span className="lsx-sl__miss">đích {fmtNum(target)} · thiếu <b>{fmtNum(thieu)}</b></span>
            : <span className="lsx-sl__full"><IcCheck /> đủ đích {fmtNum(target)}</span>
          )}
        </div>
      )}

      <div className="lsx-sl__entry">
        <label className="lsx-sl__field">
          <span className="lsx-sl__lbl">Đạt</span>
          <input className="lsx-input lsx-sl__num" inputMode="numeric" value={dat}
            onChange={(e) => setDat(digits(e.target.value))} disabled={busy}
            placeholder="0" aria-label={`Số đạt công đoạn ${s.thu_tu}`} />
        </label>
        <label className="lsx-sl__field">
          <span className="lsx-sl__lbl">Hỏng</span>
          <input className="lsx-input lsx-sl__num" inputMode="numeric" value={hong}
            onChange={(e) => setHong(digits(e.target.value))} disabled={busy}
            placeholder="0" aria-label={`Số hỏng công đoạn ${s.thu_tu}`} />
        </label>
        <div className="lsx-sl__field">
          <span className="lsx-sl__lbl" id={`dv-${s.step_id}`}>Đơn vị</span>
          <div className="lsx-caseg" role="group" aria-labelledby={`dv-${s.step_id}`}>
            {(["to", "con"] as const).map((u) => {
              const on = donVi === u;
              return (
                <button key={u} type="button" className={`lsx-caseg__btn ${on ? "is-on" : ""}`}
                  aria-pressed={on} disabled={busy} onClick={() => setDonVi(u)}>
                  {u === "to" ? "Tờ" : "Con"}
                </button>
              );
            })}
          </div>
        </div>
        <button type="button" className="btn btn--primary lsx-mini lsx-sl__save"
          disabled={busy || (dat === "" && hong === "")} onClick={submitSL}>
          <IcCheck /> Ghi
        </button>
      </div>
      <p className="lsx-sl__hint"><IcInfo /> Ghi cộng dồn — máy chỉ ghi nhận</p>

      <div className="lsx-bg">
        {next ? (
          <>
            <input className="lsx-input lsx-bg__num" inputMode="numeric" value={giao}
              onChange={(e) => setGiao(digits(e.target.value))} disabled={busy}
              placeholder={String(soDat)} aria-label={`Số giao sang ${next.to_ten ?? `công đoạn ${next.thu_tu}`}`} />
            <button type="button" className="btn btn--ghost lsx-mini lsx-bg__btn"
              disabled={busy || giaoNum <= 0} onClick={submitBG}>
              <IcPackage /> Giao sang {next.to_ten ?? `CĐ${next.thu_tu}`}
            </button>
          </>
        ) : (
          <span className="lsx-bg__last"><IcPackage /> Bước cuối — chờ nhập kho</span>
        )}
        {s.da_giao > 0 && <span className="lsx-bg__done">Đã giao <b>{fmtNum(s.da_giao)}</b></span>}
      </div>
    </div>
  );
}

// --- Lát 2 · XÁC NHẬN NHẬN (con dấu tổ nhận, lệch được kèm lý do) ---
// key theo ban_giao_id ở call-site → mỗi đợt bàn giao mới, ô số nhận reset về số giao (điền sẵn).
function NhanBlock({
  choNhan, busy, onXacNhanNhan,
}: {
  choNhan: StepChoNhan; busy: boolean;
  onXacNhanNhan: (banGiaoId: number, body: { so_nhan: number; ly_do_lech?: string | null }) => void;
}) {
  const [nhan, setNhan] = useState(() => String(choNhan.so_giao));
  const [lyDo, setLyDo] = useState("");
  const digits = (v: string) => v.replace(/[^\d]/g, "");
  const soNhan = Number(nhan || "0");
  const lech = soNhan - choNhan.so_giao;
  const unitLbl = choNhan.don_vi === "con" ? "con" : "tờ";

  return (
    <div className="lsx-nhan">
      <div className="lsx-nhan__head">
        <IcPackage />
        <span>Nhận từ <b>{choNhan.tu_to_ten ?? "tổ trước"}</b>: {fmtNum(choNhan.so_giao)} {unitLbl}</span>
      </div>
      <div className="lsx-nhan__row">
        <label className="lsx-nhan__field">
          <span className="lsx-sl__lbl">Số nhận</span>
          <input className={`lsx-input lsx-nhan__num ${lech !== 0 ? "is-lech" : ""}`} inputMode="numeric"
            value={nhan} onChange={(e) => setNhan(digits(e.target.value))} disabled={busy}
            aria-invalid={lech !== 0} aria-label="Số thực nhận" />
        </label>
        <label className="lsx-nhan__field lsx-nhan__reason">
          <span className="lsx-sl__lbl">Lý do lệch</span>
          <input className="lsx-input" type="text" value={lyDo} onChange={(e) => setLyDo(e.target.value)}
            disabled={busy} placeholder="nếu số lệch" aria-label="Lý do lệch" />
        </label>
        <button type="button" className="btn btn--primary lsx-mini lsx-nhan__ok"
          disabled={busy} onClick={() => onXacNhanNhan(choNhan.ban_giao_id, { so_nhan: soNhan, ly_do_lech: lyDo.trim() || null })}>
          <IcCheck /> Xác nhận nhận
        </button>
      </div>
      {lech !== 0 && (
        <p className="lsx-nhan__lech"><IcAlert /> lệch {lech > 0 ? "+" : ""}{fmtNum(lech)} so với số giao</p>
      )}
    </div>
  );
}
