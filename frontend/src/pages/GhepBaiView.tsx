// GHÉP BÀI — người kế hoạch chọn các LỆNH (đang nháp) → dựng 1 TỜ IN → gõ SỐ CON mỗi lệnh → tạo tờ.
// LUẬT CỨNG (user cực gắt): MÁY CHỈ GHI NHẬN. KHÔNG tự lọc "cùng giấy/khổ/màu", KHÔNG chặn, KHÔNG
// cảnh báo dư/thiếu, KHÔNG MRP. Người tự quyết ghép gì với gì + số con bao nhiêu. Giấy/khổ/màu chỉ
// HIỆN để người tự nhìn (đọc từ PTG · số con gợi ý = con/tờ engine PTG, người sửa được).
//
// Nền dữ liệu (chỉ ĐỌC, resolve như PTG resolve giấy/máy):
//   · lệnh nháp   = api.lenhSanXuat.list({ trang_thai: "nhap" })
//   · ấn phẩm/SL  = OrderLine.description/qty theo (order_id, phieu_thanh_phan_id)
//   · giấy/khổ/màu= ThanhPhan của PTG theo phieu_thanh_phan_id
//   · đã ghép tờ? = quét placements các tờ in (chỉ HIỆN nhãn, KHÔNG chặn chọn lại)
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  ApiError,
  type GhepInput,
  type GhepPlacementInput,
  type LenhSXRow,
  type OrderDetail,
  type ThanhPhanOut,
} from "../api/client";
import { giay, mayThietBi, type Row } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import { Select, type SelectOption } from "../components/Select";
import { ToastStack, useToasts } from "./LsxToast";
import "./lenh-san-xuat.css";

const maLenh = (id: number): string => `LSX-${String(id).padStart(4, "0")}`;
const fmt = (v: number | null | undefined): string =>
  typeof v === "number" ? Math.round(v).toLocaleString("vi-VN") : "—";
const toInt = (s: string): number => {
  const n = parseInt(s, 10);
  return Number.isFinite(n) && n >= 0 ? n : 0;
};

interface LenhSpec {
  giayLabel: string;   // TÊN GIẤY thật (danh mục), KHÔNG phải khổ
  khoNguyen: string;   // khổ mua (tách bạch khỏi nhãn giấy)
  khoDai: number;
  khoRong: number;
  soMauA: number;
  soMauB: number;
  soConGoiY: number;
}
interface PoolItem {
  lenh: LenhSXRow;
  anPham: string;
  khach: string;
  orderNo: string;
  targetSL: number | null;
  spec: LenhSpec | null;
  placedForms: number[];
}

function specOf(tp: ThanhPhanOut, giayById: Map<number, Row>): LenhSpec {
  // GIẤY = TÊN THẬT tra từ danh mục theo `giay_id`; chỉ lùi về khổ mua khi ấn phẩm chưa gán giấy.
  // (Trước đây lấy thẳng `kho_nguyen` làm nhãn giấy → màn ghép hiện KHỔ, hoặc "Giấy #<id>" trần.)
  const tenGiay =
    tp.giay_id != null ? String(giayById.get(tp.giay_id)?.ten ?? "").trim() : "";
  return {
    giayLabel: tenGiay || (tp.kho_nguyen ?? "").trim(),
    khoNguyen: (tp.kho_nguyen ?? "").trim(),
    khoDai: tp.kho_in_dai || 0,
    khoRong: tp.kho_in_rong || 0,
    soMauA: tp.so_mau_a || 0,
    soMauB: tp.so_mau_b || 0,
    soConGoiY: tp.so_con || 0,
  };
}
function mauLabel(s: LenhSpec | null): string {
  if (!s) return "—";
  if (s.soMauA === 0 && s.soMauB === 0) return "—";
  return s.soMauB > 0 ? `${s.soMauA}/${s.soMauB}` : `${s.soMauA}`;
}
function khoLabel(s: LenhSpec | null): string {
  if (!s || (!s.khoDai && !s.khoRong)) return "—";
  return `${fmt(s.khoDai)}×${fmt(s.khoRong)}`;
}

export function GhepBaiView({
  preselectLenhId,
  onBack,
  onOpenLenh,
}: {
  preselectLenhId?: number;
  onBack: () => void;
  onOpenLenh?: (id: number) => void;
}) {
  const { token } = useAuth();
  const toasts = useToasts();
  const [pool, setPool] = useState<PoolItem[]>([]);
  const [mays, setMays] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");

  // Khay dựng tờ: lệnh đã chọn → số con (chuỗi controlled). Map giữ THỨ TỰ chọn.
  const [tray, setTray] = useState<Map<number, string>>(new Map());
  // Thông số tờ in (ẢNH CHỤP — người gõ; auto-gợi ý từ lệnh đầu, sửa được).
  const [giayLabel, setGiayLabel] = useState("");
  const [khoDai, setKhoDai] = useState("");
  const [khoRong, setKhoRong] = useState("");
  const [soMau, setSoMau] = useState("");
  const [soKem, setSoKem] = useState("");
  const [soToChay, setSoToChay] = useState("");
  const [mayId, setMayId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const preseededRef = useRef(false);

  const load = useCallback(() => {
    if (!token) return;
    let alive = true;
    setLoading(true);
    setErr(null);
    (async () => {
      // 1) Lệnh nháp = ứng viên ghép.
      const lenhRes = await api.lenhSanXuat.list(token, { trang_thai: "nhap", size: 200 });
      const draft = lenhRes.items;
      const orderIds = [...new Set(draft.map((l) => l.order_id))];

      // 2) Nền đọc (song song, mỗi cái tự chịu lỗi): đơn (ấn phẩm/SL) · PTG (giấy/khổ/màu) ·
      //    tờ in đã ghép (nhãn "đã ghép", KHÔNG chặn) · máy.
      const [orderEntries, ptpSpec, placedMap, mayList, giayList] = await Promise.all([
        Promise.all(
          orderIds.map((oid) =>
            api.orders
              .get(token, oid)
              .then((o) => [oid, o] as const)
              .catch(() => null),
          ),
        ),
        buildPtpSpec(token),
        buildPlacedMap(token),
        mayThietBi.list(token).then((r) => r.items).catch(() => [] as Row[]),
        // Danh mục GIẤY để resolve `giay_id` → tên giấy. Endpoint gác `kho|tinh_gia_thanh|san_xuat:read`
        // nên vai Kế hoạch đọc được; thiếu quyền thì lùi êm về khổ mua (không vỡ màn).
        giay.list(token).then((r) => r.items).catch(() => [] as Row[]),
      ]);
      if (!alive) return;

      const orders = new Map<number, OrderDetail>();
      for (const e of orderEntries) if (e) orders.set(e[0], e[1]);
      const giayById = new Map<number, Row>(giayList.map((g) => [g.id, g]));

      const items: PoolItem[] = draft.map((lenh) => {
        const o = orders.get(lenh.order_id) ?? null;
        const line = o?.lines.find((ln) => ln.phieu_thanh_phan_id === lenh.phieu_thanh_phan_id) ?? null;
        const tp = lenh.phieu_thanh_phan_id != null ? ptpSpec.get(lenh.phieu_thanh_phan_id) ?? null : null;
        return {
          lenh,
          anPham: line?.description?.trim() || (lenh.phieu_thanh_phan_id ? `Ấn phẩm #${lenh.phieu_thanh_phan_id}` : "—"),
          khach: o?.customer_name ?? "—",
          orderNo: o?.order_no ?? `Đơn #${lenh.order_id}`,
          targetSL: line?.qty ?? null,
          spec: tp ? specOf(tp, giayById) : null,
          placedForms: placedMap.get(lenh.id) ?? [],
        };
      });
      setPool(items);
      setMays(mayList);
    })()
      .catch((e) => alive && setErr(e instanceof ApiError ? e.message : "Không tải được danh sách lệnh chờ ghép."))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [token]);
  useEffect(() => load(), [load]);

  const byId = useMemo(() => new Map(pool.map((p) => [p.lenh.id, p])), [pool]);

  // Preselect (vào từ detail lệnh) — seed khay 1 lần khi pool đã có.
  useEffect(() => {
    if (preseededRef.current) return;
    if (preselectLenhId == null || pool.length === 0) return;
    const item = byId.get(preselectLenhId);
    if (item) {
      preseededRef.current = true;
      setTray(new Map([[item.lenh.id, item.spec?.soConGoiY ? String(item.spec.soConGoiY) : ""]]));
      if (item.spec) seedSheet(item.spec);
    }
  }, [preselectLenhId, pool, byId]);

  function seedSheet(s: LenhSpec) {
    // Gợi ý thông số tờ từ lệnh đầu — CHỈ điền ô đang trống (không đè cái người đã gõ).
    if (s.giayLabel) setGiayLabel((g) => g || s.giayLabel);
    if (s.khoDai) setKhoDai((v) => v || String(s.khoDai));
    if (s.khoRong) setKhoRong((v) => v || String(s.khoRong));
    if (s.soMauA) setSoMau((v) => v || String(s.soMauA));
  }

  function toggle(item: PoolItem) {
    const willAdd = !tray.has(item.lenh.id);
    const wasEmpty = tray.size === 0;
    setTray((prev) => {
      const next = new Map(prev);
      if (next.has(item.lenh.id)) next.delete(item.lenh.id);
      else next.set(item.lenh.id, item.spec?.soConGoiY ? String(item.spec.soConGoiY) : "");
      return next;
    });
    // Gợi ý thông số tờ từ lệnh ĐẦU TIÊN xếp vào khay (ngoài updater — tránh setState lồng nhau).
    if (willAdd && wasEmpty && item.spec) seedSheet(item.spec);
  }
  function setCon(lenhId: number, v: string) {
    setTray((prev) => {
      const next = new Map(prev);
      next.set(lenhId, v.replace(/[^\d]/g, ""));
      return next;
    });
  }

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return pool;
    return pool.filter((p) =>
      [maLenh(p.lenh.id), p.anPham, p.khach, p.orderNo, p.spec?.giayLabel ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(s),
    );
  }, [pool, q]);

  const trayItems = useMemo(
    () => [...tray.keys()].map((id) => byId.get(id)).filter((x): x is PoolItem => !!x),
    [tray, byId],
  );

  async function submit() {
    if (!token || tray.size === 0 || submitting) return;
    setSubmitting(true);
    const placements: GhepPlacementInput[] = [...tray.entries()].map(([lenhId, con]) => ({
      lenh_sx_id: lenhId,
      so_con: toInt(con),
    }));
    const body: GhepInput = {
      giay_label: giayLabel.trim() || null,
      kho_in_dai: toInt(khoDai),
      kho_in_rong: toInt(khoRong),
      so_mau: toInt(soMau),
      so_kem: toInt(soKem),
      so_to_chay: toInt(soToChay),
      may_id: mayId,
      placements,
    };
    try {
      const form = await api.lenhSanXuat.ghep(token, body);
      toasts.ok(`Đã tạo tờ in #${form.id} · ${placements.length} lệnh xếp bài`);
      // Reset khay + thông số → dựng tờ kế; reload pool để nhãn "đã ghép" cập nhật.
      setTray(new Map());
      setGiayLabel("");
      setKhoDai("");
      setKhoRong("");
      setSoMau("");
      setSoKem("");
      setSoToChay("");
      setMayId(null);
      load();
    } catch (e) {
      toasts.err(e instanceof ApiError ? e.message : "Không tạo được tờ in.");
    } finally {
      setSubmitting(false);
    }
  }

  const mayOptions: SelectOption<number | null>[] = [
    { value: null, label: "— Chưa gán máy —" },
    ...mays.map((m) => ({
      value: m.id,
      label: String(m.ten ?? m.ma ?? `#${m.id}`),
      hint: m.ma ? String(m.ma) : undefined,
    })),
  ];

  return (
    <main className="lsx">
      <ToastStack toasts={toasts.toasts} onDismiss={toasts.dismiss} />

      <header className="lsx-head">
        <div className="lsx-head__lead">
          <button type="button" className="lsx-back" onClick={onBack}>
            <BackIcon /> Kế hoạch sản xuất
          </button>
          <div className="lsx-eyebrow" style={{ marginTop: 7 }}>
            <span className="sq" /> Sản xuất · Ghép bài
          </div>
          <h1 className="lsx-head__title">Ghép bài · dựng tờ in</h1>
          <p className="lsx-head__sub">
            Chọn các lệnh cần in, xếp chung một tờ in rồi gõ <b>số con</b> mỗi lệnh. Máy chỉ ghi nhận —
            bạn tự quyết ghép gì với gì, không có lọc/chặn tự động.
          </p>
        </div>
      </header>

      {err ? (
        <div className="banner banner--error" role="alert" style={{ marginTop: "var(--sp-3)" }}>
          <span>{err}</span>
          <button type="button" className="btn btn--ghost" style={{ padding: "4px 12px", fontSize: 12 }} onClick={load}>
            Tải lại
          </button>
        </div>
      ) : null}

      <div className="lsx-ghep">
        {/* ============ POOL: lệnh chờ ghép ============ */}
        <section className="lsx-panel lsx-ghep__pool">
          <div className="lsx-panel__hd">
            <h3>
              <LayersIcon /> Lệnh chờ ghép
            </h3>
            <span className="lsx-tag">{loading ? "…" : `${filtered.length} lệnh`}</span>
          </div>
          <div className="lsx-ghep__search">
            <SearchIcon />
            <input
              className="lsx-ghep__searchin"
              placeholder="Tìm mã lệnh, ấn phẩm, khách, giấy…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label="Tìm lệnh chờ ghép"
            />
          </div>
          <div className="lsx-ghep__poollist">
            {loading ? (
              <div className="lsx-empty lsx-empty--sm">
                <p className="lsx-empty__title">Đang tải lệnh…</p>
              </div>
            ) : filtered.length === 0 ? (
              <div className="lsx-empty lsx-empty--sm">
                <p className="lsx-empty__title">{q ? "Không có lệnh khớp tìm kiếm." : "Không còn lệnh nháp để ghép."}</p>
                <p className="lsx-empty__sub">Lệnh nháp suy từ đơn đã chốt. Ghép xong &amp; phát thì lệnh chuyển sang đang chạy.</p>
              </div>
            ) : (
              filtered.map((p) => {
                const on = tray.has(p.lenh.id);
                return (
                  <button
                    type="button"
                    key={p.lenh.id}
                    className={`lsx-pick${on ? " lsx-pick--on" : ""}`}
                    onClick={() => toggle(p)}
                    aria-pressed={on}
                  >
                    <span className={`lsx-pick__check${on ? " is-on" : ""}`} aria-hidden="true">
                      {on ? <CheckIcon /> : null}
                    </span>
                    <span className="lsx-pick__body">
                      <span className="lsx-pick__top">
                        <span className="lsx-pick__code">{maLenh(p.lenh.id)}</span>
                        {p.lenh.mau_approved_at ? (
                          <span className="lsx-stampchip lsx-stampchip--on">
                            <SealIcon /> Đã duyệt
                          </span>
                        ) : (
                          <span className="lsx-stampchip lsx-stampchip--off">
                            <ClockIcon /> Chờ duyệt
                          </span>
                        )}
                      </span>
                      <span className="lsx-pick__name">{p.anPham}</span>
                      <span className="lsx-pick__meta">
                        {p.khach} · {p.orderNo}
                        {p.targetSL != null ? ` · SL đơn ${fmt(p.targetSL)}` : ""}
                      </span>
                      <span className="lsx-specchips">
                        <span className="lsx-specchip">
                          <span className="lsx-specchip__k">Giấy</span>
                          <span className="lsx-specchip__v">{p.spec?.giayLabel || "—"}</span>
                        </span>
                        {p.spec?.khoNguyen ? (
                          <span className="lsx-specchip">
                            <span className="lsx-specchip__k">Khổ nguyên</span>
                            <span className="lsx-specchip__v">{p.spec.khoNguyen}</span>
                          </span>
                        ) : null}
                        <span className="lsx-specchip">
                          <span className="lsx-specchip__k">Khổ in</span>
                          <span className="lsx-specchip__v">{khoLabel(p.spec)}</span>
                        </span>
                        <span className="lsx-specchip">
                          <span className="lsx-specchip__k">Màu</span>
                          <span className="lsx-specchip__v">{mauLabel(p.spec)}</span>
                        </span>
                      </span>
                      {p.placedForms.length > 0 ? (
                        <span className="lsx-pick__placed">
                          <InfoDot /> Đã có trên tờ {p.placedForms.map((f) => `#${f}`).join(", ")} — vẫn ghép lại được
                        </span>
                      ) : null}
                    </span>
                  </button>
                );
              })
            )}
          </div>
        </section>

        {/* ============ TRAY: tờ in đang dựng ============ */}
        <aside className="lsx-ghep__tray">
          <div className="lsx-panel">
            <div className="lsx-panel__hd">
              <h3>
                <PrinterIcon /> Tờ in đang dựng
              </h3>
              <span className="lsx-tag">{tray.size} lệnh</span>
            </div>

            <div className="lsx-tray__list">
              {trayItems.length === 0 ? (
                <div className="lsx-empty lsx-empty--sm">
                  <p className="lsx-empty__title">Chưa chọn lệnh nào</p>
                  <p className="lsx-empty__sub">Bấm một lệnh ở cột trái để xếp vào tờ in này.</p>
                </div>
              ) : (
                trayItems.map((p) => (
                  <div key={p.lenh.id} className="lsx-trayrow">
                    <div className="lsx-trayrow__info">
                      <span className="lsx-trayrow__code">{maLenh(p.lenh.id)}</span>
                      <span className="lsx-trayrow__name">{p.anPham}</span>
                      <span className="lsx-trayrow__spec">
                        {p.spec?.giayLabel || "—"}
                        {p.spec?.khoNguyen ? ` · khổ nguyên ${p.spec.khoNguyen}` : ""} · khổ in{" "}
                        {khoLabel(p.spec)} · {mauLabel(p.spec)} màu
                        {p.targetSL != null ? ` · SL đơn ${fmt(p.targetSL)}` : ""}
                      </span>
                    </div>
                    <label className="lsx-numfield">
                      <span className="lsx-numfield__k">Số con</span>
                      <input
                        className="lsx-numin"
                        inputMode="numeric"
                        value={tray.get(p.lenh.id) ?? ""}
                        onChange={(e) => setCon(p.lenh.id, e.target.value)}
                        placeholder="0"
                        aria-label={`Số con của ${maLenh(p.lenh.id)}`}
                      />
                    </label>
                    <button
                      type="button"
                      className="lsx-iconbtn"
                      aria-label={`Bỏ ${maLenh(p.lenh.id)} khỏi tờ`}
                      onClick={() => toggle(p)}
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                        <path d="M6 6l12 12M18 6 6 18" />
                      </svg>
                    </button>
                  </div>
                ))
              )}
            </div>

            {/* Thông số tờ in (ảnh chụp — người gõ) */}
            <div className="lsx-ghep__sheet">
              <div className="lsx-ghep__sheethd">Thông số tờ in</div>
              <div className="lsx-fieldgrid">
                <label className="lsx-field lsx-field--wide">
                  <span className="lsx-field__k">Giấy</span>
                  <input className="lsx-input" value={giayLabel} onChange={(e) => setGiayLabel(e.target.value)} placeholder="VD: Couche 150 · 79×109" />
                </label>
                <label className="lsx-field">
                  <span className="lsx-field__k">Khổ in dài (mm)</span>
                  <input className="lsx-input" inputMode="numeric" value={khoDai} onChange={(e) => setKhoDai(e.target.value.replace(/[^\d]/g, ""))} placeholder="0" />
                </label>
                <label className="lsx-field">
                  <span className="lsx-field__k">Khổ in rộng (mm)</span>
                  <input className="lsx-input" inputMode="numeric" value={khoRong} onChange={(e) => setKhoRong(e.target.value.replace(/[^\d]/g, ""))} placeholder="0" />
                </label>
                <label className="lsx-field">
                  <span className="lsx-field__k">Số màu</span>
                  <input className="lsx-input" inputMode="numeric" value={soMau} onChange={(e) => setSoMau(e.target.value.replace(/[^\d]/g, ""))} placeholder="0" />
                </label>
                <label className="lsx-field">
                  <span className="lsx-field__k">Số kẽm</span>
                  <input className="lsx-input" inputMode="numeric" value={soKem} onChange={(e) => setSoKem(e.target.value.replace(/[^\d]/g, ""))} placeholder="0" />
                </label>
                <label className="lsx-field">
                  <span className="lsx-field__k">Số tờ chạy</span>
                  <input className="lsx-input" inputMode="numeric" value={soToChay} onChange={(e) => setSoToChay(e.target.value.replace(/[^\d]/g, ""))} placeholder="0" />
                </label>
                <div className="lsx-field lsx-field--wide">
                  <span className="lsx-field__k">Máy (ghi nhận máy chạy)</span>
                  <Select<number | null> options={mayOptions} value={mayId} onChange={setMayId} placeholder="— Chưa gán máy —" ariaLabel="Chọn máy chạy tờ in" portal />
                </div>
              </div>
            </div>

            <div className="lsx-ghep__foot">
              <p className="lsx-ghep__note">
                <InfoDot /> Máy chỉ ghi nhận. Không kiểm dư/thiếu, không ép cùng loại — số con &amp; cách ghép do bạn quyết.
              </p>
              <button type="button" className="btn btn--primary lsx-ghep__go" disabled={tray.size === 0 || submitting} onClick={submit}>
                {submitting ? "Đang tạo…" : `Tạo tờ in${tray.size > 0 ? ` (${tray.size} lệnh)` : ""}`}
              </button>
            </div>
          </div>

          {onOpenLenh ? (
            <div className="lsx-hint">
              <InfoDot />
              <span>
                Sau khi tạo tờ: vào chi tiết lệnh để <b>duyệt mẫu</b>, rồi <b>phát</b> tờ xuống xưởng (cần đã
                gán máy + mọi lệnh trên tờ đã duyệt mẫu).
              </span>
            </div>
          ) : null}
        </aside>
      </div>
    </main>
  );
}

// ---- Nền đọc (bounded theo tập dữ liệu kế hoạch; mỗi cái tự chịu lỗi) --------------------------
async function buildPtpSpec(token: string): Promise<Map<number, ThanhPhanOut>> {
  const map = new Map<number, ThanhPhanOut>();
  try {
    const list = await api.phieuTinhGia.list(token, {});
    const details = await Promise.all(list.items.map((p) => api.phieuTinhGia.get(token, p.id).catch(() => null)));
    for (const d of details) if (d) for (const tp of d.thanh_phans) map.set(tp.id, tp);
  } catch {
    /* thiếu quyền PTG → để trống, pool vẫn hiện (giấy/khổ/màu = —) */
  }
  return map;
}
async function buildPlacedMap(token: string): Promise<Map<number, number[]>> {
  const map = new Map<number, number[]>();
  try {
    const forms = await api.lenhSanXuat.forms(token, {});
    const details = await Promise.all(forms.items.map((f) => api.lenhSanXuat.form(token, f.id).catch(() => null)));
    for (const fd of details)
      if (fd)
        for (const pl of fd.placements) {
          const arr = map.get(pl.lenh_sx_id) ?? [];
          arr.push(fd.id);
          map.set(pl.lenh_sx_id, arr);
        }
  } catch {
    /* không đọc được tờ in → bỏ nhãn "đã ghép" (không chặn) */
  }
  return map;
}

// ---------- Inline icons (Lucide-style) ----------
const BackIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m15 18-6-6 6-6" />
  </svg>
);
const SearchIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" className="lsx-ghep__searchic" aria-hidden="true">
    <circle cx="11" cy="11" r="8" />
    <path d="m21 21-4.3-4.3" />
  </svg>
);
const LayersIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m12 3 9 5-9 5-9-5 9-5Z" />
    <path d="m3 13 9 5 9-5" />
  </svg>
);
const PrinterIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M6.5 9V3.5h11V9" />
    <rect x="4" y="9" width="16" height="8" rx="2" />
    <path d="M7 14.5h10v6H7z" />
  </svg>
);
const CheckIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20 6 9 17l-5-5" />
  </svg>
);
const SealIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 2.6 5 5.4v5.2c0 4.3 3 7.6 7 8.8 4-1.2 7-4.5 7-8.8V5.4L12 2.6Z" />
    <path d="m9 11.6 2 2 4-4.2" />
  </svg>
);
const ClockIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </svg>
);
const InfoDot = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 8h.01" />
  </svg>
);
