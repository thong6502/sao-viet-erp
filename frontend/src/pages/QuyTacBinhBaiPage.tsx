// Quy tắc bình bài — màn 3 cột (spec §9): Form + Bảng thử | Live SVG preview | Live công thức.
// File MỚI, chưa route (P4). Dùng api/binhBai.ts (module riêng, không đụng client.ts).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  binhBaiApi,
  DEFAULT_BENCH,
  DEFAULT_CONFIG,
  type LayoutMode,
  type PreviewOut,
  type RuleRow,
  type TestBench,
  type VersionConfig,
  type VersionRow,
} from "../api/binhBai";
import { useAuth } from "../auth/useAuth";
import { BinhBaiPreview } from "../components/BinhBaiPreview";
import "./quy-tac-binh-bai.css";

const MODE_LABELS: Record<LayoutMode, string> = {
  step_repeat: "Xếp con (step & repeat)",
  signature: "Bình tay sách (signature)",
  nesting: "Dàn khuôn bao bì (nesting)",
  repeat_around: "Lặp theo trục (tem cuộn)",
};
const GRAIN_LABELS: Record<string, string> = {
  none: "Không ràng buộc", canh_dai: "Canh dài", song_song_gay: "Song song gáy", theo_song: "Theo sóng",
};
const DON_GIA_KEM = 100_000; // đơn giá kẽm minh hoạ cho panel công thức (§9.5)

export function QuyTacBinhBaiPage() {
  const { token } = useAuth();
  const [rules, setRules] = useState<RuleRow[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [versions, setVersions] = useState<VersionRow[]>([]);
  const [viewVersionId, setViewVersionId] = useState<number | null>(null);

  const [ma, setMa] = useState("");
  const [ten, setTen] = useState("");
  const [moTa, setMoTa] = useState("");
  const [config, setConfig] = useState<VersionConfig>(DEFAULT_CONFIG);
  const [bench, setBench] = useState<TestBench>(DEFAULT_BENCH);

  const [preview, setPreview] = useState<PreviewOut | null>(null);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const isNew = selectedId === null;
  const currentVersion = useMemo(() => versions.find((v) => v.is_current) ?? null, [versions]);
  const viewingOld = !isNew && viewVersionId !== null && viewVersionId !== currentVersion?.id;

  const set = <K extends keyof VersionConfig>(k: K, v: VersionConfig[K]) =>
    setConfig((c) => ({ ...c, [k]: v }));
  const setB = <K extends keyof TestBench>(k: K, v: TestBench[K]) =>
    setBench((b) => ({ ...b, [k]: v }));

  // --- load rules list ---
  const loadRules = useCallback(() => {
    if (!token) return;
    binhBaiApi.list(token, { size: 200 }).then((r) => setRules(r.items)).catch(() => setRules([]));
  }, [token]);
  useEffect(() => { loadRules(); }, [loadRules]);

  // --- select a rule → load detail ---
  const selectRule = useCallback((id: number) => {
    if (!token) return;
    binhBaiApi.get(token, id).then((d) => {
      setSelectedId(d.id);
      setMa(d.ma); setTen(d.ten); setMoTa(d.mo_ta ?? "");
      setVersions(d.versions);
      const cur = d.versions.find((v) => v.is_current) ?? d.versions[0];
      setViewVersionId(cur?.id ?? null);
      if (cur) setConfig(pickConfig(cur));
    }).catch(() => { /* noop */ });
  }, [token]);

  const newRule = () => {
    setSelectedId(null); setVersions([]); setViewVersionId(null);
    setMa(""); setTen(""); setMoTa(""); setConfig(DEFAULT_CONFIG); setSaveErr(null);
  };

  const loadVersion = (vid: number) => {
    const v = versions.find((x) => x.id === vid);
    if (v) { setViewVersionId(vid); setConfig(pickConfig(v)); }
  };

  // --- debounced live preview (§9.3) ---
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (!token) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      binhBaiApi.preview(token, { config, bench })
        .then((p) => { setPreview(p); setPreviewErr(null); })
        .catch((e: Error) => { setPreview(null); setPreviewErr(e.message); });
    }, 150);
    return () => window.clearTimeout(timer.current);
  }, [token, config, bench]);

  // --- save (đẻ version mới hoặc tạo rule) ---
  const save = async () => {
    if (!token) return;
    setSaving(true); setSaveErr(null);
    try {
      if (isNew) {
        if (!ma.trim() || !ten.trim()) { setSaveErr("Nhập mã + tên quy tắc."); setSaving(false); return; }
        const row = await binhBaiApi.create(token, { ma: ma.trim(), ten: ten.trim(), mo_ta: moTa || null, config });
        loadRules(); selectRule(row.id);
      } else {
        if (ten.trim()) await binhBaiApi.updateHeader(token, selectedId!, { ten: ten.trim(), mo_ta: moTa || null });
        await binhBaiApi.createVersion(token, selectedId!, { config });
        selectRule(selectedId!); loadRules();
      }
    } catch (e) {
      setSaveErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const removeRule = async () => {
    if (!token || isNew) return;
    if (!window.confirm("Xoá quy tắc này?")) return;
    try { await binhBaiApi.remove(token, selectedId!); newRule(); loadRules(); }
    catch (e) { setSaveErr((e as Error).message); }
  };

  const money = useMemo(() => computeMoney(preview, bench), [preview, bench]);
  const mode = config.layout_mode;

  return (
    <div className="md-page qtbb">
      <div className="md-page__head">
        <h1 className="md-page__title">Quy tắc bình bài</h1>
        <div className="qtbb__topbar">
          <select className="input" value={selectedId ?? ""} onChange={(e) =>
            e.target.value ? selectRule(Number(e.target.value)) : newRule()}>
            <option value="">— Tạo quy tắc mới —</option>
            {rules.map((r) => (
              <option key={r.id} value={r.id}>{r.ma} — {r.ten}{r.trang_thai === "inactive" ? " (ẩn)" : ""}</option>
            ))}
          </select>
          {!isNew && versions.length > 0 && (
            <select className="input" value={viewVersionId ?? ""} onChange={(e) => loadVersion(Number(e.target.value))}>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>v{v.version_no}{v.is_current ? " (hiện hành)" : " (cũ, chỉ đọc)"}</option>
              ))}
            </select>
          )}
          <button className="btn btn--primary" onClick={save} disabled={saving}>
            {isNew ? "Tạo quy tắc" : "Lưu → đẻ version mới"}
          </button>
          {!isNew && <button className="btn btn--ghost" onClick={removeRule}>Xoá</button>}
        </div>
      </div>
      {saveErr && <div className="banner banner--error">{saveErr}</div>}
      {viewingOld && <div className="banner">Đang xem version cũ (chỉ đọc) — sửa & lưu sẽ đẻ version mới.</div>}

      <div className="qtbb__cols">
        {/* CỘT TRÁI — Form + Bảng thử */}
        <section className="qtbb__col qtbb__form card">
          <h3>Danh tính</h3>
          <label className="field"><span className="field__label">Mã *</span>
            <input className="input" value={ma} disabled={!isNew}
              onChange={(e) => setMa(e.target.value.toUpperCase())} placeholder="PHANG-NUP" /></label>
          <label className="field"><span className="field__label">Tên *</span>
            <input className="input" value={ten} onChange={(e) => setTen(e.target.value)} /></label>
          <label className="field"><span className="field__label">Mô tả</span>
            <textarea className="input" value={moTa} onChange={(e) => setMoTa(e.target.value)} rows={2} /></label>

          <h3>Kiểu bình bài</h3>
          <label className="field"><span className="field__label">Loại (layout_mode)</span>
            <select className="input" value={mode} onChange={(e) => set("layout_mode", e.target.value as LayoutMode)}>
              {(Object.keys(MODE_LABELS) as LayoutMode[]).map((m) => (
                <option key={m} value={m}>{MODE_LABELS[m]}</option>
              ))}
            </select></label>

          <h3>Hình học chung</h3>
          <div className="qtbb__grid2">
            <Num label="Lề hông (mm)" v={config.side_margin_mm} on={(n) => set("side_margin_mm", n)} />
            <Num label="Thang màu đuôi (mm)" v={config.tail_colorbar_mm} on={(n) => set("tail_colorbar_mm", n)} />
            <Num label="Gutter giữa con (mm)" v={config.gutter_mm} on={(n) => set("gutter_mm", n)} />
            <Num label="Bleed mặc định (mm)" v={config.bleed_default_mm} on={(n) => set("bleed_default_mm", n)} />
          </div>
          <label className="field field--check"><input type="checkbox" checked={config.allow_rotate}
            onChange={(e) => set("allow_rotate", e.target.checked)} /> Cho xoay con (2 hướng)</label>
          <label className="field"><span className="field__label">Ràng buộc thớ</span>
            <select className="input" value={config.grain_constraint}
              onChange={(e) => set("grain_constraint", e.target.value as VersionConfig["grain_constraint"])}>
              {Object.keys(GRAIN_LABELS).map((g) => <option key={g} value={g}>{GRAIN_LABELS[g]}</option>)}
            </select></label>

          {mode === "step_repeat" && (
            <>
              <h3>Step & repeat</h3>
              <label className="field field--check"><input type="checkbox" checked={config.allow_gang}
                onChange={(e) => set("allow_gang", e.target.checked)} /> Cho ghép bài (gang-run)</label>
              <Num label="Gutter tối thiểu khi ghép (mm)" v={config.min_gutter_mm} on={(n) => set("min_gutter_mm", n)} />
            </>
          )}
          {mode === "signature" && (
            <>
              <h3>Tay sách</h3>
              <label className="field"><span className="field__label">Trang/tay</span>
                <select className="input" value={config.pages_per_sig ?? ""}
                  onChange={(e) => set("pages_per_sig", e.target.value ? Number(e.target.value) : null)}>
                  <option value="">auto</option>
                  {[4, 8, 16, 32].map((n) => <option key={n} value={n}>{n}</option>)}
                </select></label>
              <label className="field"><span className="field__label">Kiểu trở</span>
                <select className="input" value={config.work_style}
                  onChange={(e) => set("work_style", e.target.value as VersionConfig["work_style"])}>
                  <option value="sheetwise">sheetwise (kẽm = tay×màu×2)</option>
                  <option value="work_turn">work & turn (kẽm = tay×màu)</option>
                </select></label>
            </>
          )}
          {mode === "nesting" && (
            <>
              <h3>Dàn khuôn</h3>
              <label className="field"><span className="field__label">Phương pháp</span>
                <select className="input" value={config.nest_method}
                  onChange={(e) => set("nest_method", e.target.value as VersionConfig["nest_method"])}>
                  <option value="grid">Lưới (grid)</option>
                  <option value="true_shape">Hình thật (true shape)</option>
                </select></label>
              <Num label="Chừa khung thải matrix (mm)" v={config.matrix_allowance_mm} on={(n) => set("matrix_allowance_mm", n)} />
            </>
          )}
          {mode === "repeat_around" && (
            <>
              <h3>Lặp theo trục</h3>
              <label className="field"><span className="field__label">Số làn (lanes)</span>
                <input className="input" type="number" value={config.lanes ?? ""} placeholder="auto"
                  onChange={(e) => set("lanes", e.target.value ? Number(e.target.value) : null)} /></label>
              <Num label="Gap quanh tem (mm)" v={config.gap_around_mm} on={(n) => set("gap_around_mm", n)} />
            </>
          )}

          <h3>Guardrails</h3>
          <div className="qtbb__grid2">
            <NumOpt label="min trang" v={config.min_pages} on={(n) => set("min_pages", n)} />
            <NumOpt label="max trang" v={config.max_pages} on={(n) => set("max_pages", n)} />
            <NumOpt label="min gáy (mm)" v={config.min_spine_mm} on={(n) => set("min_spine_mm", n)} />
          </div>

          <h3>Bảng thử (không lưu vào rule)</h3>
          <div className="qtbb__grid2">
            <Num label="Con: rộng (mm)" v={bench.rong_tp} on={(n) => setB("rong_tp", n)} />
            <Num label="Con: dài (mm)" v={bench.dai_tp} on={(n) => setB("dai_tp", n)} />
            {mode === "signature" && <NumOpt label="Số trang P" v={bench.so_trang} on={(n) => setB("so_trang", n)} />}
            {mode === "nesting" && <Num label="Blank rộng" v={bench.blank_w ?? 0} on={(n) => setB("blank_w", n)} />}
            {mode === "nesting" && <Num label="Blank dài" v={bench.blank_h ?? 0} on={(n) => setB("blank_h", n)} />}
            <Num label="Tờ nguyên: rộng (mm)" v={bench.rong_ng} on={(n) => setB("rong_ng", n)} />
            <Num label="Tờ nguyên: dài (mm)" v={bench.dai_ng} on={(n) => setB("dai_ng", n)} />
            <Num label="GSM" v={bench.gsm} on={(n) => setB("gsm", n)} />
            <Num label="Giá giấy (đ/kg)" v={bench.gia_kg} on={(n) => setB("gia_kg", n)} />
            <Num label="Nhíp máy (mm)" v={bench.gripper_mm} on={(n) => setB("gripper_mm", n)} />
            <Num label="Khổ máy tối đa W (mm, 0=∞)" v={bench.max_w} on={(n) => setB("max_w", n)} />
            {mode === "repeat_around" && <NumOpt label="Số răng trục" v={bench.teeth} on={(n) => setB("teeth", n)} />}
            {mode === "repeat_around" && <NumOpt label="Bước răng (mm)" v={bench.pitch_mm} on={(n) => setB("pitch_mm", n)} />}
            <Num label="Số lượng in" v={bench.so_luong} on={(n) => setB("so_luong", n)} />
            <Num label="Số màu trước" v={bench.so_mau_truoc} on={(n) => setB("so_mau_truoc", n)} />
            <Num label="Số màu sau" v={bench.so_mau_sau} on={(n) => setB("so_mau_sau", n)} />
          </div>
        </section>

        {/* CỘT GIỮA — Preview */}
        <section className="qtbb__col qtbb__preview card">
          <h3>Sơ đồ tờ in (live)</h3>
          <BinhBaiPreview config={config} bench={bench} preview={preview} error={previewErr} />
        </section>

        {/* CỘT PHẢI — Công thức */}
        <section className="qtbb__col qtbb__formula card">
          <h3>Công thức (live)</h3>
          {previewErr && <div className="banner banner--error">{previewErr}</div>}
          {preview && (
            <>
              <div className="qtbb__block">
                <div className="qtbb__block-h">A · Bình bài</div>
                <Row k="Loại" v={MODE_LABELS[preview.layout_mode]} />
                {preview.kho_to_in && <Row k="Khổ tờ in" v={`${fmt(preview.kho_to_in.rong)}×${fmt(preview.kho_to_in.dai)} mm (${preview.kho_to_in.kieu_cat})`} />}
                <Row k={`${unit(preview.layout_mode)}/tờ in`} v={String(preview.don_vi_per_to_in)} hi />
                <Row k="Tờ in/tờ nguyên" v={String(preview.to_in_per_nguyen)} />
                {preview.so_tay != null && <Row k="Số tay" v={String(preview.so_tay)} />}
                {preview.spine_mm != null && <Row k="Gáy (spine)" v={`${fmt(preview.spine_mm)} mm`} />}
                {preview.creep_mm != null && <Row k="Creep" v={`${fmt(preview.creep_mm)} mm`} />}
                <Row k="Hao hình học" v={`${(preview.hao_hinh_hoc_pct * 100).toFixed(1)}%`} />
              </div>
              <div className="qtbb__block">
                <div className="qtbb__block-h">B · Tác động tiền (minh hoạ)</div>
                <Row k="Tờ in cần" v={preview.so_to_in != null ? String(preview.so_to_in) : "—"} />
                <Row k="Tờ nguyên" v={preview.so_to_nguyen != null ? String(preview.so_to_nguyen) : "—"} />
                <Row k="Kg giấy" v={money ? `${fmt(money.kg)} kg` : "—"} />
                <Row k="TIỀN GIẤY" v={money ? money.tienGiay : "—"} hi />
                <Row k="Số kẽm" v={String(preview.so_kem)} />
                <Row k="TIỀN KẼM" v={money ? money.tienKem : "—"} hi />
                <div className="qtbb__note">* kẽm minh hoạ {DON_GIA_KEM.toLocaleString("vi")}đ/bản; tiền in/gia công tính ở engine tính giá (§7).</div>
              </div>
              {preview.warnings.length > 0 && (
                <div className="qtbb__block">
                  <div className="qtbb__block-h">Cảnh báo</div>
                  {preview.warnings.map((w, i) => (
                    <div key={i} className={`qtbb__warn qtbb__warn--${w.severity}`}>
                      <strong>{w.code}</strong> {w.message}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}

// --- small helpers ---
function Num({ label, v, on }: { label: string; v: number; on: (n: number) => void }) {
  return (
    <label className="field"><span className="field__label">{label}</span>
      <input className="input" type="number" value={v}
        onChange={(e) => on(e.target.value === "" ? 0 : Number(e.target.value))} /></label>
  );
}
function NumOpt({ label, v, on }: { label: string; v: number | null; on: (n: number | null) => void }) {
  return (
    <label className="field"><span className="field__label">{label}</span>
      <input className="input" type="number" value={v ?? ""} placeholder="—"
        onChange={(e) => on(e.target.value === "" ? null : Number(e.target.value))} /></label>
  );
}
function Row({ k, v, hi }: { k: string; v: string; hi?: boolean }) {
  return (
    <div className={`qtbb__row${hi ? " qtbb__row--hi" : ""}`}>
      <span className="qtbb__row-k">{k}</span><span className="qtbb__row-v">{v}</span>
    </div>
  );
}
function unit(mode: LayoutMode): string {
  return mode === "signature" ? "Tay" : mode === "nesting" ? "Blank" : mode === "repeat_around" ? "Tem" : "Con";
}
function fmt(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}
function pickConfig(v: VersionRow): VersionConfig {
  const { id, rule_id, version_no, is_current, ghi_chu_version, created_at, ...cfg } = v;
  void id; void rule_id; void version_no; void is_current; void ghi_chu_version; void created_at;
  return cfg;
}
function computeMoney(p: PreviewOut | null, b: TestBench) {
  if (!p || p.so_to_nguyen == null) return null;
  const kg = (b.rong_ng * b.dai_ng * b.gsm * p.so_to_nguyen) / 1e9; // mm×mm×gsm×tờ → kg
  const tienGiay = Math.round(kg * b.gia_kg);
  const tienKem = p.so_kem * DON_GIA_KEM;
  return { kg, tienGiay: `${tienGiay.toLocaleString("vi")}đ`, tienKem: `${tienKem.toLocaleString("vi")}đ` };
}
