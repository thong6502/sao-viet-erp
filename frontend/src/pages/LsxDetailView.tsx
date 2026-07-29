// Chi tiết 1 LỆNH SẢN XUẤT — nơi kế hoạch hoàn thiện lệnh trước khi lập kế hoạch.
// 5 tab: Thông tin chung · Quy cách (read-only từ bài tính giá) · Số lượng & bù hao · Routing · Nhật ký.
// Cột phải: checklist "còn thiếu gì" + nút "Sẵn sàng lập kế hoạch" (CTA duy nhất của màn).
//
// Trạng thái `nhap ↔ cho_bo_sung` do SERVER lật sau mỗi lần lưu — client luôn lấy lại từ response,
// không tự đoán. `san_sang` là hành động của NGƯỜI (server trả 409 nếu còn thiếu).
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  LSX_CANH_BAO_LABELS,
  LSX_THIEU_LABELS,
  api,
  type LsxActivity,
  type LsxCongDoanBody,
  type LsxDetail,
  type LsxUpdateBody,
} from "../api/client";
import { crud } from "../api/rebuildCatalog";
import { useAuth } from "../auth/useAuth";
import { useCan } from "../auth/permissions";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Icon } from "../components/Icons";
import { Timeline } from "../components/Timeline";
import { ImpositionDiagram } from "./ImpositionDiagram";
import { LsxRoutingTable, type RefRow } from "./LsxRoutingTable";
import {
  BangLoi,
  ChipGap,
  TrangThaiPill,
  classHan,
  ngay,
  ngayGio,
  num,
} from "./keHoachSxShared";

type TabKey = "chung" | "quycach" | "soluong" | "routing" | "nhatky";

const TABS: { key: TabKey; label: string }[] = [
  { key: "chung", label: "Thông tin chung" },
  { key: "quycach", label: "Quy cách" },
  { key: "soluong", label: "Số lượng & bù hao" },
  { key: "routing", label: "Công đoạn" },
  { key: "nhatky", label: "Nhật ký" },
];

const ACTION_LABEL: Record<string, string> = {
  create_lsx: "Tạo lệnh",
  update_lsx: "Sửa thông tin",
  update_lsx_routing: "Sửa công đoạn",
  lsx_trang_thai: "Đổi trạng thái",
  delete_lsx: "Xoá lệnh",
};

interface FormState {
  ten: string;
  han_hoan_thanh_sx: string;
  is_rush: boolean;
  khuon_be_id: string;
  may_id: string;
  ghi_chu: string;
  so_luong_dat: string;
  bu_hao_to: string;
  so_to_ke_hoach: string;
  so_to_nguyen: string;
  so_con: string;
}

function toForm(d: LsxDetail): FormState {
  return {
    ten: d.ten,
    han_hoan_thanh_sx: d.han_hoan_thanh_sx ?? "",
    is_rush: d.is_rush,
    khuon_be_id: d.khuon_be_id != null ? String(d.khuon_be_id) : "",
    may_id: d.may_id != null ? String(d.may_id) : "",
    ghi_chu: d.ghi_chu ?? "",
    so_luong_dat: String(d.so_luong_dat),
    bu_hao_to: String(d.bu_hao_to),
    so_to_ke_hoach: String(d.so_to_ke_hoach),
    so_to_nguyen: String(d.so_to_nguyen),
    so_con: String(d.so_con),
  };
}

export function LsxDetailView({
  lsxId,
  onBack,
  onChanged,
  navigate,
}: {
  lsxId: number;
  onBack: () => void;
  onChanged: () => void;
  navigate?: (id: string, params?: Record<string, unknown>) => void;
}) {
  const { token } = useAuth();
  const canUpdate = useCan()("san_xuat", "update");
  const [d, setD] = useState<LsxDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("chung");
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [savingRouting, setSavingRouting] = useState(false);
  const [routingDirty, setRoutingDirty] = useState(false);
  const [readyErr, setReadyErr] = useState<string | null>(null);
  const [askDelete, setAskDelete] = useState(false);
  const [acts, setActs] = useState<LsxActivity[] | null>(null);

  // Danh mục cho dropdown — nạp MỘT LẦN ở đây rồi truyền xuống bảng routing.
  const [congDoanRefs, setCongDoanRefs] = useState<RefRow[] | null>(null);
  const [toRefs, setToRefs] = useState<RefRow[] | null>(null);
  const [mayRefs, setMayRefs] = useState<RefRow[] | null>(null);
  const [khuonRefs, setKhuonRefs] = useState<RefRow[] | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setErr(null);
    api.lsx
      .get(token, lsxId)
      .then((r) => {
        setD(r);
        setForm(toForm(r));
      })
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [token, lsxId]);

  useEffect(() => load(), [load]);

  useEffect(() => {
    if (!token) return;
    // Không có quyền đọc danh mục → để null, ô hiện read-only thay vì select rỗng (select rỗng
    // + lưu = xoá trắng dữ liệu).
    api.congDoan.list(token).then((r) => setCongDoanRefs(r.items.map((c) => ({ id: c.id, ten: c.ten })))).catch(() => setCongDoanRefs(null));
    crud("/api/cong-doan/phong-ban").list(token).then((r) => setToRefs(r.items.map((t) => ({ id: t.id, ten: t.ten })))).catch(() => setToRefs(null));
    crud("/api/may-thiet-bi").list(token).then((r) => setMayRefs(r.items.map((m) => ({ id: m.id, ten: m.ten })))).catch(() => setMayRefs(null));
    api.khuonBe.list(token, { active: true }).then((r) => setKhuonRefs(r.items.map((k) => ({ id: k.id, ten: k.ten })))).catch(() => setKhuonRefs(null));
  }, [token]);

  // Nhật ký nạp LƯỜI — chỉ khi mở tab.
  useEffect(() => {
    if (tab !== "nhatky" || !token || acts !== null) return;
    api.lsx.activity(token, lsxId).then((r) => setActs(r.items)).catch(() => setActs([]));
  }, [tab, token, lsxId, acts]);

  const dirty = useMemo(() => {
    if (!d || !form) return false;
    return JSON.stringify(form) !== JSON.stringify(toForm(d));
  }, [d, form]);

  function set<K extends keyof FormState>(k: K, v: FormState[K]) {
    setForm((prev) => (prev ? { ...prev, [k]: v } : prev));
  }

  async function luu() {
    if (!token || !form || !d) return;
    setSaving(true);
    setErr(null);
    const body: LsxUpdateBody = {
      ten: form.ten,
      han_hoan_thanh_sx: form.han_hoan_thanh_sx || null,
      is_rush: form.is_rush,
      ghi_chu: form.ghi_chu || null,
      so_luong_dat: Number(form.so_luong_dat || 0),
      bu_hao_to: Number(form.bu_hao_to || 0),
      so_to_ke_hoach: Number(form.so_to_ke_hoach || 0),
      so_to_nguyen: Number(form.so_to_nguyen || 0),
      so_con: Number(form.so_con || 1),
    };
    // Chỉ gửi khoá/máy khi danh mục đọc được — tránh xoá trắng dữ liệu server đang giữ.
    if (khuonRefs) body.khuon_be_id = form.khuon_be_id ? Number(form.khuon_be_id) : null;
    if (mayRefs) body.may_id = form.may_id ? Number(form.may_id) : null;
    try {
      const r = await api.lsx.update(token, d.id, body);
      setD(r);
      setForm(toForm(r));
      setActs(null);
      onChanged();
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  /** Gợi ý SL vào/ra chạy ngược từ SL thành phẩm — CHỈ ĐỌC, bảng tự hỏi người dùng có áp không. */
  const tinhNguoc = useCallback(async () => {
    if (!token || !d) return [];
    return (await api.lsx.tinhNguoc(token, d.id)).rows;
  }, [token, d]);

  /** Bộ mặc định của công đoạn mới khi kế hoạch đổi 1 bước — luật ở backend, client chỉ áp. */
  const macDinhBuoc = useCallback(
    async (congDoanId: number) => {
      if (!token || !d) throw new Error("chưa sẵn sàng");
      return api.lsx.macDinhBuoc(token, d.id, congDoanId);
    },
    [token, d],
  );

  async function luuRouting(body: LsxCongDoanBody[], lyDo?: string) {
    if (!token || !d) return;
    setSavingRouting(true);
    setErr(null);
    try {
      const r = await api.lsx.saveRouting(token, d.id, body, lyDo);
      setD(r);
      setForm(toForm(r));
      setActs(null);
      setRoutingDirty(false);
      onChanged();
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSavingRouting(false);
    }
  }

  async function doiTrangThai(tt: "nhap" | "san_sang") {
    if (!token || !d) return;
    setReadyErr(null);
    try {
      const r = await api.lsx.setTrangThai(token, d.id, tt);
      setD(r);
      setForm(toForm(r));
      setActs(null);
      onChanged();
    } catch (e: unknown) {
      setReadyErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function xoa() {
    if (!token || !d) return;
    try {
      await api.lsx.remove(token, d.id);
      onChanged();
      onBack();
    } catch (e: unknown) {
      setErr(e instanceof ApiError ? e.message : String(e));
      setAskDelete(false);
    }
  }

  if (loading) {
    // Skeleton GIỮ ĐÚNG layout (head + 2 cột) để nội dung thật không làm nhảy trang.
    return (
      <div className="khsx-detail" role="status" aria-live="polite">
        <span className="sr-only">Đang tải lệnh sản xuất…</span>
        <header className="khsx-detail__head">
          <span className="khsx-skel__bar khsx-skel__bar--title" />
          <span className="khsx-skel__bar khsx-skel__bar--sub" />
        </header>
        <div className="khsx-detail__grid">
          <div className="khsx-detail__main">
            <span className="khsx-skel__bar" />
            <span className="khsx-skel__bar" />
            <span className="khsx-skel__bar" />
          </div>
          <aside className="khsx-aside">
            <span className="khsx-skel__bar khsx-skel__bar--card" />
          </aside>
        </div>
      </div>
    );
  }
  if (!d || !form) {
    return (
      <div className="khsx-detail__gone">
        <BangLoi text={err ?? "Lệnh không còn tồn tại (có thể đã bị xoá)."} />
        <Button variant="secondary" onClick={onBack}>
          ‹ Về danh sách lệnh
        </Button>
      </div>
    );
  }

  const qc = (d.quy_cach_json ?? {}) as Record<string, unknown>;
  const n = (k: string): number => Number(qc[k] ?? 0);
  const s = (k: string): string => (qc[k] == null || qc[k] === "" ? "—" : String(qc[k]));
  const coBinhBai = n("kho_in_dai") > 0 && n("kho_in_rong") > 0 && n("dai_thanh_pham") > 0 && n("rong_thanh_pham") > 0;
  const chuaMm =
    n("chua_xen") + n("chua_tay_ke") + n("chua_nhip") + n("chua_duoi") + n("chua_ca_gay");
  const canKhuon = d.cong_doans.some((c) => /bế|cấn/i.test(c.ten));
  const goiYToIn = d.so_con > 0 ? Math.ceil(d.so_luong_dat / d.so_con) + Number(form.bu_hao_to || 0) : 0;
  const lechToIn = goiYToIn > 0 && Number(form.so_to_ke_hoach || 0) !== goiYToIn;
  const hanTre =
    !!form.han_hoan_thanh_sx && !!d.han_giao_khach && form.han_hoan_thanh_sx >= d.han_giao_khach;

  return (
    <div className="khsx-detail">
      <header className="khsx-detail__head">
        <button type="button" className="khsx-back" onClick={onBack}>
          ‹ Quay lại danh sách lệnh
        </button>
        <p className="eyebrow">Sản xuất · Lệnh sản xuất</p>
        <div className="khsx-detail__titlerow">
          <h1 className="khsx-detail__ma">{d.ma}</h1>
          <TrangThaiPill tt={d.trang_thai} lg />
          {d.is_rush && <ChipGap />}
          <div className="khsx-detail__spacer" />
          {canUpdate && d.trang_thai !== "san_sang" && (
            <Button variant="ghost" className="khsx-btn--danger" onClick={() => setAskDelete(true)}>
              <Icon name="trash" size={14} /> Xoá lệnh
            </Button>
          )}
        </div>
        <p className="khsx-detail__name">{d.ten}</p>
        <p className="khsx-detail__meta">
          {d.order_no && (
            <button
              type="button"
              className="khsx-xlink"
              onClick={() => navigate?.("don-hang-ban", { openOrderId: d.order_id })}
            >
              Đơn {d.order_no}
            </button>
          )}
          {d.customer_name && <span> · {d.customer_name}</span>}
          {d.customer_po_no && <span> · PO {d.customer_po_no}</span>}
          {d.quote_number && (
            <span>
              {" "}· Báo giá {d.quote_number}
              {d.quote_version_number ? ` v${d.quote_version_number}` : ""}
            </span>
          )}
          {d.ptg_ma && (
            <>
              {" · "}
              <button
                type="button"
                className="khsx-xlink"
                onClick={() => navigate?.("tinh-gia", { focusPhieuId: d.ptg_id })}
              >
                {d.ptg_ma}
              </button>
            </>
          )}
        </p>
      </header>

      {err && <BangLoi text={err} onRetry={load} />}

      <div className="khsx-detail__grid">
        <div className="khsx-detail__main">
          <div className="khsx-tabs" role="tablist" aria-label="Nội dung lệnh sản xuất">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                id={`khsx-tab-${t.key}`}
                aria-selected={tab === t.key}
                aria-controls={`khsx-panel-${t.key}`}
                className={`khsx-tabs__btn ${tab === t.key ? "is-active" : ""}`}
                onClick={() => setTab(t.key)}
              >
                {t.label}
                {((t.key === "routing" && routingDirty) ||
                  ((t.key === "chung" || t.key === "soluong") && dirty)) && (
                  <span className="khsx-tabs__dot" aria-label="có thay đổi chưa lưu" />
                )}
              </button>
            ))}
          </div>

          {tab === "chung" && (
            <section className="khsx-panel" role="tabpanel" id="khsx-panel-chung" aria-labelledby="khsx-tab-chung" tabIndex={0}>
              <div className="khsx-form">
                <label className="khsx-field">
                  <span className="khsx-field__label">Tên lệnh</span>
                  <input value={form.ten} onChange={(e) => set("ten", e.target.value)} />
                </label>
                <label className="khsx-field">
                  <span className="khsx-field__label">Hạn hoàn thành sản xuất</span>
                  <input
                    type="date"
                    value={form.han_hoan_thanh_sx}
                    onChange={(e) => set("han_hoan_thanh_sx", e.target.value)}
                  />
                  {hanTre && (
                    <span className="khsx-field__warn">
                      Hạn sản xuất nên sớm hơn hạn giao khách ít nhất 1 ngày
                    </span>
                  )}
                </label>
                <label className="khsx-field khsx-field--check">
                  <input
                    type="checkbox"
                    checked={form.is_rush}
                    onChange={(e) => set("is_rush", e.target.checked)}
                  />
                  <span>Hàng GẤP — ưu tiên ở xưởng</span>
                </label>
                {canKhuon && (
                  <label className="khsx-field">
                    <span className="khsx-field__label">Khuôn bế</span>
                    {khuonRefs ? (
                      <select value={form.khuon_be_id} onChange={(e) => set("khuon_be_id", e.target.value)}>
                        <option value="">— chưa gán —</option>
                        {khuonRefs.map((k) => (
                          <option key={k.id} value={k.id}>
                            {k.ten}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="khsx-kv__val">{d.khuon_be_ten ?? "—"}</span>
                    )}
                  </label>
                )}
                <label className="khsx-field">
                  <span className="khsx-field__label">
                    Máy in dự kiến
                    {d.may_id != null && <span className="khsx-field__origin">đề xuất</span>}
                  </span>
                  {mayRefs ? (
                    <select value={form.may_id} onChange={(e) => set("may_id", e.target.value)}>
                      <option value="">— chưa gán —</option>
                      {mayRefs.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.ten}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="khsx-kv__val">{d.may_ten ?? "—"}</span>
                  )}
                </label>
                <label className="khsx-field khsx-field--wide">
                  <span className="khsx-field__label">Ghi chú kế hoạch</span>
                  <textarea rows={3} value={form.ghi_chu} onChange={(e) => set("ghi_chu", e.target.value)} />
                </label>
              </div>

              <div className="khsx-kvgrid">
                <KV k="Đơn hàng" v={d.order_no ?? "—"} />
                <KV k="Khách hàng" v={d.customer_name ?? "—"} />
                <KV k="Sale phụ trách" v={d.sale_name ?? "—"} />
                <KV k="Người phụ trách KH" v={d.nguoi_phu_trach_ten ?? "—"} />
                <KV k="Hạn giao khách" v={ngay(d.han_giao_khach)} mono />
                <KV k="Bàn giao lúc" v={ngayGio(d.ban_giao_at)} mono />
                <KV k="Tạo lúc" v={ngayGio(d.created_at)} mono />
                <KV k="Sửa lúc" v={ngayGio(d.updated_at)} mono />
              </div>
            </section>
          )}

          {tab === "quycach" && (
            <section className="khsx-panel" role="tabpanel" id="khsx-panel-quycach" aria-labelledby="khsx-tab-quycach" tabIndex={0}>
              <p className="khsx-callout khsx-callout--steel">
                <Icon name="help" size={14} />
                <span>
                  Quy cách chốt từ bài tính giá {d.ptg_ma ?? ""} — sửa ở phiếu tính giá, không sửa tại
                  đây.
                </span>
                {d.ptg_id && (
                  <button
                    type="button"
                    className="khsx-xlink"
                    onClick={() => navigate?.("tinh-gia", { focusPhieuId: d.ptg_id })}
                  >
                    Mở phiếu tính giá →
                  </button>
                )}
              </p>

              <h4 className="khsx-spec__head">Thành phẩm</h4>
              <div className="khsx-kvgrid">
                <KV k="Dài × rộng (mm)" v={`${num(n("dai_thanh_pham"))} × ${num(n("rong_thanh_pham"))}`} mono />
                <KV k="Khổ thành phẩm" v={s("kho_thanh_pham")} />
                <KV k="Khổ mở rộng" v={s("kho_mo_rong")} />
                <KV k="Tay gấp" v={s("tay_gap")} />
                <KV k="Số tờ / sản phẩm" v={num(n("so_to_per_sp"))} mono />
              </div>

              <h4 className="khsx-spec__head">Giấy &amp; tờ in</h4>
              <div className="khsx-kvgrid">
                <KV k="Giấy" v={s("giay_ten")} />
                <KV k="Định lượng (gsm)" v={qc.gsm ? num(n("gsm")) : "—"} mono />
                <KV k="Nguồn giấy" v={qc.nguon_giay === "khach" ? "Khách cấp" : "Công ty"} />
                <KV k="Khổ giấy nguyên (mm)" v={`${num(n("kho_nguyen_dai"))} × ${num(n("kho_nguyen_rong"))}`} mono />
                <KV k="Khổ tờ in (mm)" v={`${num(n("kho_in_dai"))} × ${num(n("kho_in_rong"))}`} mono />
                <KV k="Cách in" v={s("quy_cach_in")} />
                <KV k="Số màu A / B" v={`${num(n("so_mau_a"))} / ${num(n("so_mau_b"))}`} mono />
                <KV k="Tổng chừa (mm)" v={num(chuaMm)} mono />
              </div>

              <h4 className="khsx-spec__head">Bình bài</h4>
              <div className="khsx-kvgrid">
                <KV k="Con / tờ" v={num(n("so_con"))} mono />
                <KV k="Số mảnh xả" v={num(n("so_manh_xa"))} mono />
                <KV k="Số kẽm" v={num(n("so_kem"))} mono />
                <KV k="Số lượt in" v={num(n("so_luot"))} mono />
              </div>

              {coBinhBai && (
                <div className="khsx-spec__diagram">
                  <ImpositionDiagram
                    khoInDai={n("kho_in_dai")}
                    khoInRong={n("kho_in_rong")}
                    daiTP={n("dai_thanh_pham")}
                    rongTP={n("rong_thanh_pham")}
                    chuaMm={chuaMm}
                    soCon={n("so_con")}
                  />
                </div>
              )}

              {qc.ghi_chu_ky_thuat ? (
                <p className="khsx-spec__note">
                  <Icon name="bell" size={13} /> Ghi chú kỹ thuật: {String(qc.ghi_chu_ky_thuat)}
                </p>
              ) : null}
            </section>
          )}

          {tab === "soluong" && (
            <section className="khsx-panel" role="tabpanel" id="khsx-panel-soluong" aria-labelledby="khsx-tab-soluong" tabIndex={0}>
              <div className="khsx-form">
                <label className="khsx-field">
                  <span className="khsx-field__label">Số lượng khách đặt ({d.don_vi_tinh})</span>
                  <input
                    type="number"
                    value={form.so_luong_dat}
                    onChange={(e) => set("so_luong_dat", e.target.value)}
                  />
                </label>
                <label className="khsx-field">
                  <span className="khsx-field__label">Bù hao (tờ)</span>
                  <input type="number" value={form.bu_hao_to} onChange={(e) => set("bu_hao_to", e.target.value)} />
                </label>
                <label className="khsx-field">
                  <span className="khsx-field__label">
                    Số tờ kế hoạch<span className="khsx-field__origin">đề xuất</span>
                  </span>
                  <input
                    type="number"
                    value={form.so_to_ke_hoach}
                    onChange={(e) => set("so_to_ke_hoach", e.target.value)}
                  />
                </label>
                <label className="khsx-field">
                  <span className="khsx-field__label">Số tờ giấy nguyên</span>
                  <input
                    type="number"
                    value={form.so_to_nguyen}
                    onChange={(e) => set("so_to_nguyen", e.target.value)}
                  />
                </label>
                <label className="khsx-field">
                  <span className="khsx-field__label">Con / tờ</span>
                  <input type="number" value={form.so_con} onChange={(e) => set("so_con", e.target.value)} />
                </label>
              </div>

              <p className="khsx-qty__derive">
                Tờ in = ⌈{num(d.so_luong_dat)} ÷ {num(d.so_con)}⌉ + bù hao {num(Number(form.bu_hao_to || 0))} →{" "}
                <strong>{num(goiYToIn)} tờ</strong>
              </p>
              {lechToIn && (
                <p className="khsx-qty__mismatch">
                  Số bạn nhập ({num(Number(form.so_to_ke_hoach || 0))}) khác số máy tính ra.
                  <button
                    type="button"
                    className="khsx-xlink"
                    onClick={() => set("so_to_ke_hoach", String(goiYToIn))}
                  >
                    Dùng số máy tính
                  </button>
                </p>
              )}
            </section>
          )}

          {tab === "routing" && (
            <section className="khsx-panel" role="tabpanel" id="khsx-panel-routing" aria-labelledby="khsx-tab-routing" tabIndex={0}>
              <LsxRoutingTable
                congDoans={d.cong_doans}
                soToKeHoach={d.so_to_ke_hoach}
                soLuongDat={d.so_luong_dat}
                soCon={d.so_con}
                leadTime={d.lead_time}
                congDoanRefs={congDoanRefs}
                toRefs={toRefs}
                mayRefs={mayRefs}
                canUpdate={canUpdate}
                saving={savingRouting}
                onSave={luuRouting}
                onTinhNguoc={tinhNguoc}
                onMacDinhBuoc={macDinhBuoc}
                onDirtyChange={setRoutingDirty}
              />
            </section>
          )}

          {tab === "nhatky" && (
            <section className="khsx-panel" role="tabpanel" id="khsx-panel-nhatky" aria-labelledby="khsx-tab-nhatky" tabIndex={0}>
              {acts === null ? (
                <p className="khsx-muted">Đang tải nhật ký…</p>
              ) : (
                <Timeline
                  emptyText="Chưa có hoạt động."
                  items={acts.map((a) => ({
                    title: a.detail || ACTION_LABEL[a.action] || a.action,
                    meta: `${a.actor_name ?? "—"} · ${ngayGio(a.at)}`,
                    accent: a.action === "create_lsx" || a.action === "lsx_trang_thai",
                  }))}
                />
              )}
            </section>
          )}
        </div>

        <aside className="khsx-aside">
          <div
            className={`khsx-ready ${
              d.trang_thai === "san_sang"
                ? "khsx-ready--done"
                : d.thieu.length
                ? "khsx-ready--blocked"
                : "khsx-ready--ok"
            }`}
          >
            {d.trang_thai === "san_sang" ? (
              <>
                <p className="khsx-ready__title">
                  <Icon name="check" size={15} /> Đã sẵn sàng lập kế hoạch.
                </p>
                <Button variant="ghost" block onClick={() => doiTrangThai("nhap")}>
                  Mở lại để sửa
                </Button>
              </>
            ) : d.thieu.length ? (
              <>
                <p className="khsx-ready__title">Còn thiếu {d.thieu.length} mục</p>
                <ul className="khsx-ready__list" id="khsx-ready-list">
                  {d.thieu.map((code) => (
                    <li key={code} className="khsx-ready__item">
                      <Icon name="x" size={12} />
                      <span>{LSX_THIEU_LABELS[code] ?? code}</span>
                      {code === "thieu_khuon" && (
                        <button type="button" className="khsx-xlink" onClick={() => setTab("chung")}>
                          Sửa →
                        </button>
                      )}
                      {code === "thieu_routing" && (
                        <button type="button" className="khsx-xlink" onClick={() => setTab("routing")}>
                          Sửa →
                        </button>
                      )}
                      {(code === "thieu_giay" || code === "thieu_kho") && (
                        <button type="button" className="khsx-xlink" onClick={() => setTab("quycach")}>
                          Xem →
                        </button>
                      )}
                      {(code === "thieu_ngay_giao" || code === "khong_co_ptg") && (
                        <button
                          type="button"
                          className="khsx-xlink"
                          onClick={() => navigate?.("don-hang-ban", { openOrderId: d.order_id })}
                        >
                          Mở đơn →
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
                <Button variant="accent" block disabled aria-describedby="khsx-ready-list">
                  Sẵn sàng lập kế hoạch
                </Button>
              </>
            ) : (
              <>
                <p className="khsx-ready__title">
                  <Icon name="check" size={15} /> Đủ dữ liệu.
                </p>
                <Button variant="accent" block onClick={() => doiTrangThai("san_sang")}>
                  Sẵn sàng lập kế hoạch
                </Button>
              </>
            )}
            {readyErr && <BangLoi text={readyErr} onRetry={load} />}
          </div>

          {/* Rổ MỀM — tách hẳn khỏi checklist chặn ở trên: đây là nghi vấn nghề, người kế hoạch
              đọc rồi tự quyết, hệ thống KHÔNG chặn phát hành vì mấy dòng này. */}
          {d.canh_bao.length > 0 && (
            <div className="khsx-luuy">
              <p className="khsx-luuy__title">
                <Icon name="help" size={14} /> Lưu ý ({d.canh_bao.length})
              </p>
              <ul className="khsx-luuy__list">
                {d.canh_bao.map((code) => (
                  <li key={code}>
                    <span>{LSX_CANH_BAO_LABELS[code] ?? code}</span>
                    {(code === "dut_chuyen" || code === "ra_lon_hon_vao"
                      || code === "khac_bai_tinh_gia" || code === "vuot_han_giao") && (
                      <button type="button" className="khsx-xlink" onClick={() => setTab("routing")}>
                        Xem →
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              <p className="khsx-luuy__foot">Không chặn — bạn vẫn đánh dấu sẵn sàng được.</p>
            </div>
          )}

          <div className="khsx-facts">
            <Fact k="SL đặt" v={`${num(d.so_luong_dat)} ${d.don_vi_tinh}`} />
            <Fact k="Bù hao" v={`${num(d.bu_hao_to)} tờ`} />
            <Fact k="Tờ in" v={num(d.so_to_ke_hoach)} />
            <Fact k="Tờ nguyên" v={num(d.so_to_nguyen)} />
            <Fact k="Con / tờ" v={num(d.so_con)} />
            <Fact k="Công đoạn" v={num(d.cong_doans.length)} />
            <Fact k="Hạn giao khách" v={ngay(d.han_giao_khach)} cls={classHan(d.han_giao_khach)} />
            <Fact k="Hạn SX nội bộ" v={ngay(d.han_hoan_thanh_sx)} cls={classHan(d.han_hoan_thanh_sx)} />
          </div>

          {dirty && (
            <div className="khsx-aside__save">
              <p>Có thay đổi chưa lưu</p>
              <div className="khsx-aside__savebtns">
                <Button variant="ghost" onClick={() => setForm(toForm(d))}>
                  Hoàn tác
                </Button>
                <Button variant="primary" loading={saving} onClick={luu}>
                  Lưu
                </Button>
              </div>
            </div>
          )}
        </aside>
      </div>

      <ConfirmDialog
        open={askDelete}
        title={`Xoá lệnh ${d.ma}?`}
        message="Lệnh chưa phát hành nên xoá được. Dòng đơn sẽ quay lại hàng chờ để lên lệnh lại."
        confirmLabel="Xoá lệnh"
        danger
        onConfirm={xoa}
        onCancel={() => setAskDelete(false)}
      />
    </div>
  );
}

function KV({ k, v, mono = false }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="khsx-kv">
      <span className="khsx-kv__key">{k}</span>
      <span className={`khsx-kv__val ${mono ? "khsx-num" : ""}`}>{v}</span>
    </div>
  );
}

function Fact({ k, v, cls = "" }: { k: string; v: string; cls?: string }) {
  return (
    <div className="khsx-fact">
      <span className="khsx-fact__label">{k}</span>
      <span className={`khsx-fact__value ${cls}`}>{v}</span>
    </div>
  );
}
