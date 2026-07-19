// DETAIL của "Kế hoạch sản xuất" — 1 LỆNH SẢN XUẤT (cấu hình → phát xuống xưởng).
// Dữ liệu record-only (BE): lệnh + bài con + routing + tờ in + đích SL. Tên ấn phẩm/máy/công đoạn/tổ
// resolve qua danh mục (orders · máy · công đoạn · phòng ban). Xếp bài (ghép đa-khách) đọc thêm
// form_detail cho từng tờ. (Module theo dõi thực thi xưởng — sản lượng/bàn giao/QC — đã gỡ.)
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  ApiError,
  type KhuonBeRow,
  type LenhSXDetailOut,
  type OrderDetail,
  type PrintFormDetailOut,
  type PrintFormRow,
  type Department,
  type RoutingStepRow,
} from "../api/client";
import { congDoan, mayThietBi, type Row } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import { Select, type SelectOption } from "../components/Select";
import { AnPhamDrawer } from "./AnPhamDrawer";
import { LenhSanXuatPrint } from "./LenhSanXuatPrint";
import { ToastStack, useToasts } from "./LsxToast";
import { hanGiao } from "../utils/format";
import "./lenh-san-xuat.css";

// Cổng PHÁT (mirror _form_readiness ở service): đã ghép ≥1 lệnh + đã gán máy + mọi lệnh duyệt mẫu.
// Tính CLIENT-SIDE chỉ để HIỆN blocker sớm; backend vẫn là nguồn chân lý (422 khi bấm phát non).
function formReadiness(
  f: PrintFormRow,
  fd: PrintFormDetailOut | undefined,
): { ready: boolean; blockers: string[]; isPhat: boolean } {
  const isPhat = f.trang_thai === "da_phat" || f.trang_thai === "in_xong";
  const blockers: string[] = [];
  if ((fd?.placements.length ?? 0) === 0) blockers.push("Chưa ghép lệnh nào");
  if (f.may_id == null) blockers.push("Chưa gán máy");
  const chuaDuyet = (fd?.lenhs ?? []).filter((l) => !l.mau_approved_at).length;
  if (chuaDuyet > 0) blockers.push(`Còn ${chuaDuyet} lệnh chưa duyệt mẫu`);
  return { ready: blockers.length === 0, blockers, isPhat };
}

const fmt = (v: number | null | undefined): string =>
  typeof v === "number" ? Math.round(v).toLocaleString("vi-VN") : "—";

const maLenh = (id: number): string => `LSX-${String(id).padStart(4, "0")}`;

function fmtDate(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("vi-VN");
}
function fmtDateTime(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  return isNaN(d.getTime())
    ? "—"
    : d.toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

const LENH_META: Record<string, { label: string; variant: string }> = {
  nhap: { label: "Nháp", variant: "neutral" },
  dang_chay: { label: "Đang chạy", variant: "run" },
  xong: { label: "Xong", variant: "done" },
  huy: { label: "Hủy", variant: "danger" },
};
const PF_META: Record<string, { label: string; variant: string }> = {
  cho_ghep: { label: "Chờ ghép", variant: "neutral" },
  du_dieu_kien: { label: "Đủ điều kiện", variant: "info" },
  da_phat: { label: "Đã phát", variant: "run" },
  in_xong: { label: "In xong", variant: "done" },
};
const metaOf = (m: Record<string, { label: string; variant: string }>, k: string) =>
  m[k] ?? { label: k || "—", variant: "neutral" };

export function LenhSanXuatDetailView({
  id,
  onBack,
  onGhep,
}: {
  id: number;
  onBack: () => void;
  onGhep: (lenhId: number) => void;
}) {
  const { token } = useAuth();
  const toasts = useToasts();
  const [detail, setDetail] = useState<LenhSXDetailOut | null>(null);
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [mays, setMays] = useState<Map<number, Row>>(new Map());
  const [congDoans, setCongDoans] = useState<Map<number, Row>>(new Map());
  const [depts, setDepts] = useState<Map<number, Department>>(new Map());
  const [formDetails, setFormDetails] = useState<Map<number, PrintFormDetailOut>>(new Map());
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null); // khoá nút đang chạy: "duyet" | `may-<id>` | `phat-<id>`
  // Drawer chi tiết ấn phẩm: giữ cả itemId (bài con) → drawer SỬA được khi lệnh nháp.
  const [drawer, setDrawer] = useState<{ ptp: number; itemId: number | null } | null>(null);
  // Bản in lệnh sản xuất: khổ thành phẩm fetch theo từng bài con khi mở in.
  const [showPrint, setShowPrint] = useState(false);
  const [khoTP, setKhoTP] = useState<Map<number, string>>(new Map());
  // ③ Danh mục khuôn bế (chỉ nạp khi lệnh CÓ công đoạn bế → cần gán khuôn).
  const [khuonList, setKhuonList] = useState<KhuonBeRow[]>([]);

  const load = useCallback(() => {
    if (!token) return;
    let alive = true;
    setLoading(true);
    setErr(null);
    api.lenhSanXuat
      .get(token, id)
      .then(async (d) => {
        if (!alive) return;
        setDetail(d);
        // Enrichment — mỗi cái tự chịu lỗi (thiếu quyền/đơn) để phần lõi lệnh vẫn hiện.
        const [ord, may, cd, dept, khuon] = await Promise.all([
          api.orders.get(token, d.order_id).catch(() => null),
          mayThietBi.list(token).then((r) => r.items).catch(() => [] as Row[]),
          congDoan.list(token).then((r) => r.items).catch(() => [] as Row[]),
          api.rbac.departments(token).catch(() => [] as Department[]),
          // Khuôn chỉ nạp khi lệnh có bế (cần gán khuôn); vai không có quyền khuon_be → [].
          d.can_khuon ? api.khuonBe.list(token).then((r) => r.items).catch(() => [] as KhuonBeRow[]) : Promise.resolve([] as KhuonBeRow[]),
        ]);
        if (!alive) return;
        setOrder(ord);
        setMays(new Map(may.map((m) => [m.id, m])));
        setCongDoans(new Map(cd.map((c) => [c.id, c])));
        setDepts(new Map(dept.map((x) => [x.id, x])));
        setKhuonList(khuon);
        const forms = await Promise.all(
          d.forms.map((f) => api.lenhSanXuat.form(token, f.id).catch(() => null)),
        );
        if (!alive) return;
        setFormDetails(
          new Map(forms.filter((f): f is PrintFormDetailOut => !!f).map((f) => [f.id, f])),
        );
      })
      .catch((e) => alive && setErr(e instanceof ApiError ? e.message : "Không tải được lệnh sản xuất."))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [token, id]);
  useEffect(() => load(), [load]);

  const mayName = useCallback(
    (mid: number | null): string | null => {
      if (mid == null) return null;
      const m = mays.get(mid);
      return m ? String(m.ten ?? m.ma ?? `#${mid}`) : `Máy #${mid}`;
    },
    [mays],
  );
  const cdName = useCallback(
    (cid: number | null): string => {
      if (cid == null) return "—";
      const c = congDoans.get(cid);
      return c ? String(c.ten_hien_thi ?? c.ten ?? `#${cid}`) : `Công đoạn #${cid}`;
    },
    [congDoans],
  );
  const toName = useCallback(
    (tid: number | null): string => {
      if (tid == null) return "—";
      const d = depts.get(tid);
      return d ? d.name : `Tổ #${tid}`;
    },
    [depts],
  );

  const mayOptions: SelectOption<number | null>[] = useMemo(
    () => [
      { value: null, label: "— Chưa gán máy —" },
      ...[...mays.values()].map((m) => ({
        value: m.id,
        label: String(m.ten ?? m.ma ?? `#${m.id}`),
        hint: m.ma ? String(m.ma) : undefined,
      })),
    ],
    [mays],
  );
  const cdOptions: SelectOption<number | null>[] = useMemo(
    () =>
      [...congDoans.values()].map((c) => ({
        value: c.id,
        label: String(c.ten_hien_thi ?? c.ten ?? `#${c.id}`),
      })),
    [congDoans],
  );

  // --- Thao tác (Chunk 7): duyệt mẫu (lệnh) · gán máy / phát (tờ in). Sau mỗi cái → refetch + toast. ---
  async function doDuyetMau() {
    if (!token || !detail || busy) return;
    setBusy("duyet");
    try {
      await api.lenhSanXuat.duyetMau(token, detail.id);
      toasts.ok(`Đã duyệt mẫu ${maLenh(detail.id)}`);
      load();
    } catch (e) {
      toasts.err(e instanceof ApiError ? e.message : "Không duyệt được mẫu.");
    } finally {
      setBusy(null);
    }
  }
  async function doGanMay(formId: number, may: number | null) {
    if (!token || busy) return;
    setBusy(`may-${formId}`);
    try {
      await api.lenhSanXuat.ganMay(token, formId, may);
      toasts.ok(may == null ? `Đã gỡ máy khỏi tờ in #${formId}` : `Đã gán máy cho tờ in #${formId}`);
      load();
    } catch (e) {
      toasts.err(e instanceof ApiError ? e.message : "Không gán được máy.");
    } finally {
      setBusy(null);
    }
  }
  async function doPhat(formId: number) {
    if (!token || busy) return;
    setBusy(`phat-${formId}`);
    try {
      await api.lenhSanXuat.phat(token, formId);
      toasts.ok(`Đã phát tờ in #${formId} xuống xưởng`);
      load();
    } catch (e) {
      // 422 = cổng AND chưa đủ (chưa gán máy / còn lệnh chưa duyệt) → hiện rõ blocker của backend.
      toasts.err(e instanceof ApiError ? e.message : "Không phát được tờ in.");
    } finally {
      setBusy(null);
    }
  }
  // PHÁT HÀNH LỆNH (cấp lệnh): phát mọi tờ in đủ điều kiện của lệnh → lệnh sang đang chạy, các tổ
  // trong routing nhận việc (backend phát theo tờ + broadcast real-time; đích danh tổ = chunk D).
  async function doPhatHanh() {
    if (!token || !detail || busy) return;
    const targets = detail.forms.filter((f) => {
      const rd = formReadiness(f, formDetails.get(f.id));
      return rd.ready && !rd.isPhat;
    });
    if (targets.length === 0) return;
    setBusy("phat-hanh");
    try {
      for (const f of targets) await api.lenhSanXuat.phat(token, f.id);
      toasts.ok(`Đã phát hành ${maLenh(detail.id)} — các tổ trong routing nhận việc`);
      load();
    } catch (e) {
      toasts.err(e instanceof ApiError ? e.message : "Không phát hành được lệnh.");
    } finally {
      setBusy(null);
    }
  }
  // --- CẤU HÌNH routing trên lệnh (§13.2): kế thừa từ tính giá là MẶC ĐỊNH, ở đây SỬA được khi nháp
  // (thêm/bớt/đổi thứ tự/đổi tổ). Backend khóa bước đã/đang chạy (409). Sau mỗi thao tác → refetch. ---
  async function doThemBuoc(congDoanId: number) {
    if (!token || !detail || busy) return;
    const cd = congDoans.get(congDoanId);
    const dep = cd?.department_id != null ? Number(cd.department_id) : null;
    setBusy("routing");
    try {
      await api.lenhSanXuat.themBuoc(token, detail.id, { cong_doan_id: congDoanId, to_id: dep });
      load();
    } catch (e) {
      toasts.err(e instanceof ApiError ? e.message : "Không thêm được công đoạn.");
    } finally {
      setBusy(null);
    }
  }
  async function doXoaBuoc(step: RoutingStepRow) {
    if (!token || busy) return;
    setBusy(`rs-${step.id}`);
    try {
      await api.lenhSanXuat.xoaBuoc(token, step.id);
      load();
    } catch (e) {
      toasts.err(e instanceof ApiError ? e.message : "Không xóa được công đoạn.");
    } finally {
      setBusy(null);
    }
  }
  async function doReorder(index: number, dir: -1 | 1) {
    if (!token || !detail || busy) return;
    const steps = [...detail.routing];
    const j = index + dir;
    if (j < 0 || j >= steps.length) return;
    [steps[index], steps[j]] = [steps[j], steps[index]];
    setBusy("routing");
    try {
      await api.lenhSanXuat.reorderRouting(token, detail.id, steps.map((s) => s.id));
      load();
    } catch (e) {
      toasts.err(e instanceof ApiError ? e.message : "Không đổi được thứ tự.");
    } finally {
      setBusy(null);
    }
  }
  // ① Kế hoạch SỬA hạn giao (khách/nội bộ) — CHỈ khi lệnh nháp (save on-blur). Sau phát: BE trả 409.
  async function saveHan(body: { han_giao_khach?: string | null; han_giao_noi_bo?: string | null }) {
    if (!token || !detail || busy) return;
    setBusy("han-giao");
    try {
      await api.lenhSanXuat.suaHanGiao(token, detail.id, body);
      toasts.ok("Đã cập nhật hạn giao");
      load();
    } catch (e) {
      toasts.err(
        e instanceof ApiError && e.isConflict
          ? "Lệnh đã phát, không đổi hạn"
          : e instanceof ApiError
            ? e.message
            : "Không cập nhật được hạn giao.",
      );
    } finally {
      setBusy(null);
    }
  }

  // ③ Điều độ gán/gỡ khuôn bế (record-only — cảnh báo mềm, không chặn phát).
  async function saveKhuon(khuonBeId: number | null) {
    if (!token || !detail || busy) return;
    setBusy("khuon");
    try {
      await api.lenhSanXuat.ganKhuon(token, detail.id, khuonBeId);
      toasts.ok(khuonBeId ? "Đã gán khuôn bế" : "Đã gỡ khuôn bế");
      load();
    } catch (e) {
      toasts.err(e instanceof ApiError ? e.message : "Không cập nhật được khuôn bế.");
    } finally {
      setBusy(null);
    }
  }

  // Mở bản in: fetch khổ thành phẩm cho từng bài con (chỉ kỹ thuật, backend đã lọc giá).
  async function openPrint() {
    if (!token) return;
    const entries = await Promise.all(
      (detail?.items ?? []).map(async (it) => {
        if (it.id == null || it.phieu_thanh_phan_id == null) return null;
        try {
          const d = await api.lenhSanXuat.anPhamChiTiet(token, it.phieu_thanh_phan_id, it.id);
          // Nhãn khổ tự do thường trống → fallback sang khổ số dài×rộng (mm).
          const kho =
            d.kho_thanh_pham?.trim() ||
            (d.dai_thanh_pham && d.rong_thanh_pham ? `${d.dai_thanh_pham}×${d.rong_thanh_pham} mm` : "—");
          return [it.id, kho] as const;
        } catch {
          return [it.id, "—"] as const;
        }
      }),
    );
    setKhoTP(new Map(entries.filter((e): e is readonly [number, string] => e != null)));
    setShowPrint(true);
  }

  const lenhBadge = detail ? metaOf(LENH_META, detail.trang_thai) : null;
  const muc = detail?.muc_tieu_sl ?? 0;

  // Quy cách in gợi nhìn: đọc từ tờ in đầu tiên (job spec — record ở tờ in).
  const firstForm = detail?.forms?.[0] ?? null;

  // Ngữ cảnh đơn (đọc sống từ Đơn) để kế hoạch cấu hình đúng: tên ấn phẩm + SL + gấp + lưu ý SX.
  const anPhamLine =
    order?.lines?.find((l) => l.phieu_thanh_phan_id === detail?.phieu_thanh_phan_id) ?? null;

  // Chế độ CẤU HÌNH (nháp) ↔ THỰC THI (đang chạy/xong): nháp ẩn khối runtime, hiện nút Phát hành.
  const isConfig = detail?.trang_thai === "nhap";
  // Gợi ý hạn nội bộ = khách − 1 ngày (chỉ text, KHÔNG auto-điền). Rỗng nếu chưa có hạn khách.
  const suggestNoiBo = useMemo(() => {
    const s = detail?.han_giao_khach;
    if (!s) return "";
    const d = new Date(s);
    if (isNaN(d.getTime())) return "";
    d.setDate(d.getDate() - 1);
    const dd = String(d.getDate()).padStart(2, "0");
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    return `${dd}/${mm}/${d.getFullYear()}`;
  }, [detail?.han_giao_khach]);
  const phatTargets = detail
    ? detail.forms.filter((f) => {
        const rd = formReadiness(f, formDetails.get(f.id));
        return rd.ready && !rd.isPhat;
      })
    : [];
  const phatBlockers = detail
    ? Array.from(
        new Set([
          ...(detail.forms.length === 0 ? ["Chưa ghép tờ in nào"] : []),
          ...detail.forms.flatMap((f) => {
            const rd = formReadiness(f, formDetails.get(f.id));
            return rd.isPhat ? [] : rd.blockers;
          }),
        ]),
      )
    : [];
  const canPhatHanh = phatTargets.length > 0 && phatBlockers.length === 0;

  return (
    <main className="lsx">
      <header className="lsx-head">
        <div className="lsx-head__lead">
          <button type="button" className="lsx-back" onClick={onBack}>
            <BackIcon /> Danh sách lệnh
          </button>
          <div className="lsx-eyebrow" style={{ marginTop: 7 }}>
            <span className="sq" /> Sản xuất · Lệnh sản xuất
          </div>
          <div className="lsx-head__titlerow">
            <h1 className="lsx-head__title">{maLenh(id)}</h1>
            {lenhBadge ? (
              <span className={`lsx-badge lsx-badge--${lenhBadge.variant}`}>
                <span className="lsx-badge__d" />
                {lenhBadge.label}
              </span>
            ) : null}
            {detail?.mau_approved_at ? (
              <span className="lsx-stampchip lsx-stampchip--on">
                <SealIcon /> Đã duyệt mẫu
              </span>
            ) : null}
          </div>
        </div>
        {detail ? (
          <div className="lsx-head__actions">
            <button type="button" className="btn btn--secondary" onClick={openPrint}>
              <PrinterIcon /> Xem bản in
            </button>
            {detail.trang_thai !== "huy" && !detail.mau_approved_at ? (
              <button type="button" className="btn btn--secondary" disabled={busy === "duyet"} onClick={doDuyetMau}>
                <SealIcon /> {busy === "duyet" ? "Đang duyệt…" : "Duyệt mẫu"}
              </button>
            ) : null}
            {isConfig ? (
              <button type="button" className="btn btn--secondary" onClick={() => onGhep(detail.id)}>
                <LayersIcon /> Ghép bài
              </button>
            ) : null}
            {isConfig ? (
              <button
                type="button"
                className="btn btn--primary"
                disabled={busy != null || !canPhatHanh}
                onClick={doPhatHanh}
                title={canPhatHanh
                  ? "Phát hành lệnh — các tổ trong routing nhận việc"
                  : `Chưa đủ điều kiện: ${phatBlockers.join(" · ")}`}
              >
                <SendIcon /> {busy === "phat-hanh" ? "Đang phát hành…" : "Phát hành lệnh"}
              </button>
            ) : null}
          </div>
        ) : null}
      </header>
      <ToastStack toasts={toasts.toasts} onDismiss={toasts.dismiss} />

      {err ? (
        <div className="banner banner--error" role="alert" style={{ marginTop: "var(--sp-3)" }}>
          <span>{err}</span>
          <button type="button" className="btn btn--ghost" style={{ padding: "4px 12px", fontSize: 12 }} onClick={load}>
            Tải lại
          </button>
        </div>
      ) : null}

      {loading && !detail ? (
        <div className="lsx-empty" style={{ marginTop: "var(--sp-5)" }}>
          <p className="lsx-empty__title">Đang tải lệnh…</p>
        </div>
      ) : detail ? (
        <div className="lsx-split">
          {/* ============ LEFT ============ */}
          <div className="lsx-main">
            {/* --- Ấn phẩm trong lệnh: các bài con (giữ chi tiết khi gom) → drawer quy cách + routing gốc --- */}
            <section className="lsx-panel">
              <div className="lsx-panel__hd">
                <h3><PackageIcon /> Ấn phẩm trong lệnh</h3>
                <span className="lsx-tag">{detail.items.length} bài</span>
              </div>
              <div className="lsx-panel__body">
                {detail.items.length === 0 ? (
                  <div className="lsx-empty lsx-empty--sm">
                    <p className="lsx-empty__title">Chưa có ấn phẩm</p>
                    <p className="lsx-empty__sub">Lệnh này chưa gắn bài con nào.</p>
                  </div>
                ) : (
                  <div className="lsx-book__rows">
                    {detail.items.map((it, i) => {
                      const ptp = it.phieu_thanh_phan_id;
                      const open = () => ptp != null && setDrawer({ ptp, itemId: it.id });
                      return (
                        <div
                          key={ptp ?? `x${i}`}
                          className="lsx-rec lsx-rec--plain"
                          role={ptp != null ? "button" : undefined}
                          tabIndex={ptp != null ? 0 : -1}
                          onClick={open}
                          onKeyDown={(e) => {
                            if (ptp != null && (e.key === "Enter" || e.key === " ")) {
                              e.preventDefault();
                              open();
                            }
                          }}
                          style={ptp == null ? { cursor: "default" } : undefined}
                        >
                          <div className="lsx-rec__nameblk">
                            <span className="lsx-rec__name">{it.ten || `Ấn phẩm #${ptp ?? "—"}`}</span>
                          </div>
                          <div className="lsx-rec__qty">
                            <span className="lsx-rec__qtyn">{fmt(it.qty)}</span>
                            <span className="lsx-rec__qtyu">{it.don_vi_tinh}</span>
                          </div>
                          {ptp != null ? (
                            <span className="lsx-rec__chev" aria-hidden="true">
                              <ChevIcon />
                            </span>
                          ) : (
                            <span className="lsx-rec__chev" aria-hidden="true" />
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </section>

            {/* --- Routing công đoạn (§13.2): kế thừa từ tính giá; CẤU HÌNH khi nháp (thêm/bớt/đổi thứ tự). Tổ ăn theo công đoạn. --- */}
            <section className="lsx-panel">
              <div className="lsx-panel__hd">
                <h3><FlowIcon /> Routing công đoạn</h3>
                <span className="lsx-tag">{detail.routing.length} bước</span>
              </div>
              <div className="lsx-panel__body">
                {detail.routing.length === 0 ? (
                  <div className="lsx-empty lsx-empty--sm">
                    <p className="lsx-empty__title">Chưa có routing</p>
                    <p className="lsx-empty__sub">
                      Routing kế thừa từ phiếu tính giá khi bung lệnh; ở đây cấu hình được khi lệnh còn nháp.
                    </p>
                  </div>
                ) : (
                  <ol className="lsx-trav">
                    {detail.routing.map((s, i) => {
                      const last = i === detail.routing.length - 1;
                      const editable = isConfig;
                      return (
                        <li key={s.id} className="lsx-trav__step lsx-trav__step--neutral">
                          <div className="lsx-trav__rail">
                            <span className="lsx-trav__node" aria-hidden="true">
                              <span className="lsx-trav__no">{i + 1}</span>
                            </span>
                            {last ? null : <span className="lsx-trav__line" />}
                          </div>
                          <div className="lsx-trav__body">
                            <div className="lsx-trav__top">
                              <span className="lsx-trav__ten">{s.ten || cdName(s.cong_doan_id)}</span>
                              {editable ? (
                                <div className="lsx-trav__ops">
                                  <button type="button" className="lsx-iconbtn" disabled={i === 0 || busy != null} onClick={() => doReorder(i, -1)} aria-label="Đưa lên">↑</button>
                                  <button type="button" className="lsx-iconbtn" disabled={last || busy != null} onClick={() => doReorder(i, 1)} aria-label="Đưa xuống">↓</button>
                                  <button type="button" className="lsx-iconbtn lsx-iconbtn--danger" disabled={busy != null} onClick={() => doXoaBuoc(s)} aria-label="Xóa công đoạn">✕</button>
                                </div>
                              ) : null}
                            </div>
                            {/* Tổ ăn theo công đoạn (khai ở module Công đoạn) — chỉ HIỂN THỊ, không chọn ở đây. */}
                            <span className="lsx-trav__to">
                              {s.to_id != null ? (
                                <><UsersIcon /> {toName(s.to_id)}</>
                              ) : (
                                <span className="lsx-trav__unset">tổ theo công đoạn</span>
                              )}
                            </span>
                            {s.quy_cach ? <div className="lsx-qc"><SpecIcon /> {s.quy_cach}</div> : null}
                            {s.ghi_chu ? <div className="lsx-stepnote"><NoteIcon /> {s.ghi_chu}</div> : null}
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                )}
                {isConfig ? (
                  <div className="lsx-routing__add">
                    <Select<number | null>
                      options={cdOptions}
                      value={null}
                      onChange={(v) => { if (v != null) doThemBuoc(v); }}
                      placeholder="+ Thêm công đoạn vào routing…"
                      ariaLabel="Thêm công đoạn vào routing"
                      disabled={busy != null}
                      portal
                    />
                  </div>
                ) : null}
              </div>
            </section>

            {/* --- Tờ in & xếp bài --- */}
            <section className="lsx-panel">
              <div className="lsx-panel__hd">
                <h3><PrinterIcon /> Tờ in &amp; xếp bài</h3>
                <span className="lsx-tag">{detail.forms.length} tờ</span>
              </div>
              <div className="lsx-panel__body">
                {detail.forms.length === 0 ? (
                  <div className="lsx-empty lsx-empty--sm">
                    <p className="lsx-empty__title">Chưa ghép tờ in</p>
                    <p className="lsx-empty__sub">
                      Người kế hoạch ghép lệnh vào tờ in (1 lượt chạy máy) rồi gán máy &amp; phát.
                    </p>
                  </div>
                ) : (
                  <div className="lsx-forms">
                    {detail.forms.map((f) => {
                      const pf = metaOf(PF_META, f.trang_thai);
                      const fd = formDetails.get(f.id);
                      return (
                        <div key={f.id} className="lsx-form">
                          <div className="lsx-form__hd">
                            <span className="lsx-form__code">
                              <PrinterIcon /> Tờ in #{f.id}
                            </span>
                            <span className={`lsx-badge lsx-badge--${pf.variant}`}>
                              <span className="lsx-badge__d" />
                              {pf.label}
                            </span>
                          </div>
                          <div className="lsx-form__spec">
                            <Spec k="Giấy" v={f.giay_label || "—"} sans />
                            <Spec k="Khổ in" v={f.kho_in_dai || f.kho_in_rong ? `${fmt(f.kho_in_dai)}×${fmt(f.kho_in_rong)} mm` : "—"} />
                            <Spec k="Số màu" v={f.so_mau > 0 ? String(f.so_mau) : "—"} />
                            <Spec k="Số kẽm" v={f.so_kem > 0 ? String(f.so_kem) : "—"} />
                            <Spec k="Máy" v={mayName(f.may_id) ?? "chưa gán"} sans />
                            <Spec k="Tờ chạy" v={f.so_to_chay > 0 ? fmt(f.so_to_chay) : "—"} />
                          </div>
                          {fd && fd.placements.length > 0 ? (
                            <div className="lsx-gang">
                              <div className="lsx-gang__label">
                                <LayersIcon /> Xếp bài trên tờ ({fd.placements.length} lệnh ghép chung)
                              </div>
                              <div className="lsx-gang__chips">
                                {fd.placements.map((p) => {
                                  const self = p.lenh_sx_id === id;
                                  return (
                                    <span key={p.id} className={`lsx-gangchip${self ? " lsx-gangchip--self" : ""}`}>
                                      <b>{maLenh(p.lenh_sx_id)}</b>
                                      <span className="lsx-gangchip__con">×{fmt(p.so_con)} con</span>
                                      {self ? <span className="muted">· lệnh này</span> : null}
                                    </span>
                                  );
                                })}
                              </div>
                            </div>
                          ) : null}
                          {(() => {
                            const rd = formReadiness(f, fd);
                            return (
                              <div className="lsx-formactions">
                                <div className="lsx-formactions__may">
                                  <span className="lsx-formactions__k">Máy chạy</span>
                                  <Select<number | null>
                                    options={mayOptions}
                                    value={f.may_id}
                                    onChange={(v) => doGanMay(f.id, v)}
                                    placeholder="— Chưa gán máy —"
                                    ariaLabel={`Gán máy cho tờ in #${f.id}`}
                                    disabled={rd.isPhat || busy != null}
                                    portal
                                  />
                                </div>
                                <div className="lsx-formactions__go">
                                  {!rd.isPhat && rd.blockers.length > 0 ? (
                                    <ul className="lsx-blockers">
                                      {rd.blockers.map((b, i) => (
                                        <li key={i}>
                                          <WarnDot /> {b}
                                        </li>
                                      ))}
                                    </ul>
                                  ) : null}
                                  {rd.isPhat ? (
                                    <span className="lsx-phatdone">
                                      <CheckDot /> Đã phát xuống xưởng
                                    </span>
                                  ) : (
                                    <button
                                      type="button"
                                      className="btn btn--primary lsx-phatbtn"
                                      disabled={busy === `phat-${f.id}`}
                                      onClick={() => doPhat(f.id)}
                                    >
                                      {busy === `phat-${f.id}` ? "Đang phát…" : "Phát xuống xưởng"}
                                    </button>
                                  )}
                                </div>
                              </div>
                            );
                          })()}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </section>

          </div>

          {/* ============ RIGHT (sticky) ============ */}
          <aside className="lsx-side">
            {/* Dark card: nháp = chưa phát hành · đã phát = đã xuống xưởng (đích SL + tờ in + routing) */}
            <div className="lsx-dk">
              <div className="lsx-dk__hd">
                <div className="lsx-dk__eyebrow"><GaugeIcon /> {isConfig ? "Trạng thái lệnh" : "Lệnh đã phát"}</div>
              </div>
              <div className="lsx-dk__cfg">
                <div className="lsx-dk__cfgttl">{isConfig ? "Chưa phát hành" : "Đã phát xuống xưởng"}</div>
                <p className="lsx-dk__cfgsub">
                  {isConfig
                    ? <>Cấu hình xong (ghép tờ · gán máy · duyệt mẫu) rồi bấm <b>Phát hành lệnh</b> — các tổ trong routing sẽ nhận việc.</>
                    : <>Lệnh đã phát — các tổ trong routing đã nhận việc theo tờ in đã phát.</>}
                </p>
                <div className="lsx-dk__rows">
                  <div className="lsx-drow"><span className="k">Đích sản lượng</span><span className="v">{muc > 0 ? fmt(muc) : "chưa xác định"}</span></div>
                  <div className="lsx-drow"><span className="k">Tờ in đã ghép</span><span className="v">{detail.forms.length}</span></div>
                  <div className="lsx-drow"><span className="k">Bước routing</span><span className="v">{detail.routing.length}</span></div>
                </div>
              </div>
            </div>

            {/* Lệnh này */}
            <section className="lsx-panel">
              <div className="lsx-panel__hd"><h3><FileIcon /> Lệnh này</h3></div>
              <div className="lsx-info">
                <div className="lsx-irow"><span className="k">Mã lệnh</span><span className="v mono">{maLenh(id)}</span></div>
                <div className="lsx-irow"><span className="k">Đơn hàng</span><span className="v mono">{order?.order_no ?? `#${detail.order_id}`}</span></div>
                <div className="lsx-irow"><span className="k">Khách hàng</span><span className="v">{order?.customer_name ?? "—"}</span></div>
                {isConfig ? (
                  <div className="lsx-irow" style={{ flexDirection: "column", alignItems: "stretch", gap: 8 }}>
                    <span className="k">Hạn giao</span>
                    <div className="lsx-dw__form">
                      <div className="lsx-dw__field">
                        <span className="lsx-dw__flabel"><FlagIcon /> Giao khách</span>
                        <input
                          type="date"
                          className="lsx-dw__in"
                          defaultValue={(detail.han_giao_khach ?? "").slice(0, 10)}
                          onBlur={(e) => saveHan({ han_giao_khach: e.target.value || null })}
                        />
                      </div>
                      <div className="lsx-dw__field">
                        <span className="lsx-dw__flabel"><ClockIcon /> Nội bộ (mục tiêu)</span>
                        <input
                          type="date"
                          className="lsx-dw__in"
                          defaultValue={(detail.han_giao_noi_bo ?? "").slice(0, 10)}
                          onBlur={(e) => saveHan({ han_giao_noi_bo: e.target.value || null })}
                        />
                        {suggestNoiBo ? (
                          <span className="lsx-dw__sub">Gợi ý: {suggestNoiBo} (khách − 1 ngày)</span>
                        ) : null}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="lsx-irow">
                    <span className="k">Hạn giao</span>
                    <div className="lsx-duestack lsx-duestack--end">
                      {(() => {
                        const nb = hanGiao(detail.han_giao_noi_bo ?? detail.han_giao_khach);
                        return nb ? (
                          <span className={`lsx-due lsx-due--${nb.level}`}><ClockIcon /> {nb.label}</span>
                        ) : (
                          <span className="muted">—</span>
                        );
                      })()}
                      {detail.han_giao_noi_bo && detail.han_giao_khach ? (
                        <span className="lsx-hardline"><FlagIcon /> Khách <b>{fmtDate(detail.han_giao_khach)}</b></span>
                      ) : null}
                      {order?.is_rush ? (
                        <span className="lsx-badge lsx-badge--danger">
                          <span className="lsx-badge__d" /> GẤP
                        </span>
                      ) : null}
                    </div>
                  </div>
                )}
                <div className="lsx-irow">
                  <span className="k">Ấn phẩm</span>
                  <span className="v">
                    {anPhamLine?.description || (detail.phieu_thanh_phan_id ? `Ấn phẩm #${detail.phieu_thanh_phan_id}` : "—")}
                    {anPhamLine ? (
                      <span className="mono" style={{ color: "var(--ash)", marginLeft: 6 }}>
                        · {fmt(anPhamLine.qty)} {anPhamLine.don_vi_tinh}
                      </span>
                    ) : null}
                  </span>
                </div>
                <div className="lsx-irow"><span className="k">Máy gán</span><span className="v">{mayName(detail.may_id) ?? "chưa gán"}</span></div>
                {detail.can_khuon ? (
                  <div className="lsx-irow" style={{ flexDirection: "column", alignItems: "stretch", gap: 6 }}>
                    <span className="k">Khuôn bế</span>
                    {!detail.khuon_be_id ? (
                      <div className="lsx-hc__note" style={{ margin: 0 }}>
                        <NoteIcon /><span>Chưa gán khuôn bế — chọn khuôn để chuẩn bị phát.</span>
                      </div>
                    ) : null}
                    <Select<number | null>
                      options={[
                        { value: null, label: "— chưa gán —" },
                        ...khuonList.map((k) => ({
                          value: k.id as number | null,
                          label: `${k.ma} · ${k.ten}${k.so_ke ? ` · kệ ${k.so_ke}` : ""}`,
                        })),
                      ]}
                      value={detail.khuon_be_id ?? null}
                      onChange={(v) => saveKhuon(v)}
                      placeholder="Chọn khuôn bế…"
                      ariaLabel="Gán khuôn bế cho lệnh"
                      disabled={busy != null}
                      portal
                    />
                  </div>
                ) : null}
                {firstForm ? (
                  <div className="lsx-irow"><span className="k">Quy cách in</span><span className="v mono">{firstForm.so_mau > 0 ? `${firstForm.so_mau} màu` : "—"}{firstForm.kho_in_dai ? ` · ${fmt(firstForm.kho_in_dai)}×${fmt(firstForm.kho_in_rong)}` : ""}</span></div>
                ) : null}
                <div className="lsx-irow"><span className="k">Tạo lúc</span><span className="v mono">{fmtDateTime(detail.created_at)}</span></div>
              </div>
              {order?.production_note || detail.ghi_chu_ky_thuat ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 6, margin: "var(--sp-2) var(--sp-4) 0" }}>
                  {order?.production_note ? (
                    <div className="lsx-hc__note">
                      <NoteIcon /><span><strong>Lưu ý SX:</strong> {order.production_note}</span>
                    </div>
                  ) : null}
                  {detail.ghi_chu_ky_thuat ? (
                    <div className="lsx-hc__note">
                      <NoteIcon /><span><strong>Kỹ thuật:</strong> {detail.ghi_chu_ky_thuat}</span>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </section>

            {/* Con dấu duyệt mẫu */}
            {detail.mau_approved_at ? (
              <section className="lsx-panel">
                <div className="lsx-panel__hd"><h3><SealIcon /> Duyệt mẫu</h3></div>
                <div className="lsx-stamp">
                  <span className="lsx-stamp__ic"><SealIcon /></span>
                  <div className="lsx-stamp__body">
                    <div className="lsx-stamp__title">Đã duyệt mẫu</div>
                    <div className="lsx-stamp__who">
                      {detail.mau_approved_snapshot?.ten || "—"}
                      {detail.mau_approved_snapshot?.chuc_vu ? ` · ${detail.mau_approved_snapshot.chuc_vu}` : ""}
                      {detail.mau_approved_snapshot?.to ? ` · ${detail.mau_approved_snapshot.to}` : ""}
                    </div>
                    <div className="lsx-stamp__meta">{fmtDateTime(detail.mau_approved_at)}</div>
                  </div>
                </div>
              </section>
            ) : (
              <section className="lsx-panel">
                <div className="lsx-panel__hd"><h3><SealIcon /> Duyệt mẫu</h3></div>
                <div className="lsx-stamp lsx-stamp--off">
                  <span className="lsx-stamp__ic"><ClockIcon /></span>
                  <div className="lsx-stamp__body">
                    <div className="lsx-stamp__title">Chờ duyệt mẫu</div>
                    <div className="lsx-stamp__who">Cổng phát tờ in yêu cầu mọi lệnh trên tờ đã duyệt mẫu.</div>
                  </div>
                </div>
              </section>
            )}

          </aside>
        </div>
      ) : null}

      {drawer != null && token ? (
        <AnPhamDrawer
          token={token}
          ptpId={drawer.ptp}
          lenhItemId={drawer.itemId}
          ctx={{ orderNo: order?.order_no ?? undefined, khach: order?.customer_name ?? undefined }}
          cdName={cdName}
          mayName={mayName}
          onClose={() => setDrawer(null)}
          onSaved={load}
        />
      ) : null}

      {showPrint && detail ? (
        <LenhSanXuatPrint
          detail={detail}
          order={order}
          mayName={mayName}
          cdName={cdName}
          toName={toName}
          formDetails={formDetails}
          khoTP={khoTP}
          onClose={() => setShowPrint(false)}
        />
      ) : null}
    </main>
  );
}

// ---------- Small blocks ----------
function Spec({ k, v, sans }: { k: string; v: string; sans?: boolean }) {
  return (
    <div className="lsx-specitem">
      <span className="lsx-specitem__k">{k}</span>
      <span className={`lsx-specitem__v${sans ? " sans" : ""}`}>{v}</span>
    </div>
  );
}

// ---------- Inline icons (Lucide-style) ----------
const BackIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m15 18-6-6 6-6" />
  </svg>
);
const PackageIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 8 12 3 3 8v8l9 5 9-5V8Z" />
    <path d="m3 8 9 5 9-5M12 13v8" />
  </svg>
);
const ChevIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m9 6 6 6-6 6" />
  </svg>
);
const SealIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 2.6 5 5.4v5.2c0 4.3 3 7.6 7 8.8 4-1.2 7-4.5 7-8.8V5.4L12 2.6Z" />
    <path d="m9 11.6 2 2 4-4.2" />
  </svg>
);
const ClockIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </svg>
);
const FlowIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4 7h11M4 7l3-3M4 7l3 3" />
    <path d="M20 17H9M20 17l-3-3M20 17l-3 3" />
  </svg>
);
const PrinterIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M6.5 9V3.5h11V9" />
    <rect x="4" y="9" width="16" height="8" rx="2" />
    <path d="M7 14.5h10v6H7z" />
  </svg>
);
const GaugeIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 14 15 9" />
    <path d="M3.5 18a9 9 0 1 1 17 0" />
    <circle cx="12" cy="14" r="1.4" fill="currentColor" stroke="none" />
  </svg>
);
const FileIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M14 2.6H7A2 2 0 0 0 5 4.6v14.8a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7.6Z" />
    <path d="M14 2.6V7.6h5" />
    <path d="M8.5 13h7M8.5 16.5h4" />
  </svg>
);
const LayersIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m12 3 9 5-9 5-9-5 9-5Z" />
    <path d="m3 13 9 5 9-5" />
  </svg>
);
const WarnDot = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M10.3 3.9 2.4 18a1.9 1.9 0 0 0 1.7 2.9h15.8a1.9 1.9 0 0 0 1.7-2.9L13.7 3.9a1.9 1.9 0 0 0-3.4 0Z" />
    <path d="M12 9v4M12 16.5h.01" />
  </svg>
);
const CheckDot = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20 6 9 17l-5-5" />
  </svg>
);
const UsersIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="3.2" />
    <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
  </svg>
);
const SendIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M22 2 11 13" />
    <path d="M22 2 15 22l-4-9-9-4 20-7Z" />
  </svg>
);
const FlagIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
    <path d="M4 22v-7" />
  </svg>
);
const NoteIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M15.5 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L15.5 3Z" />
    <path d="M15 3v5h5M8.5 12.5h7M8.5 16h5" />
  </svg>
);
const SpecIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="3" y="8" width="18" height="8" rx="1.5" />
    <path d="M7 8v3M11 8v4M15 8v3M19 8v4" />
  </svg>
);
