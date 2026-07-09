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
import { Button } from "../components/Button";
import "./master-data.css";
import "./rebuild-catalog.css";
import "./quy-tac-binh-bai.css";

const MODE_LABELS: Record<LayoutMode, string> = {
  step_repeat: "Xếp con (step & repeat)",
  signature: "Bình tay sách (signature)",
  nesting: "Dàn khuôn bao bì (nesting)",
};
const MODE_HINT: Record<LayoutMode, string> = {
  step_repeat: "Xếp nhiều con giống nhau — name card, tờ rơi, poster, tem rời.",
  signature: "Gấp tay sách — sách, catalogue, tạp chí nhiều trang.",
  nesting: "Dàn khuôn từ dieline — hộp giấy, bao bì.",
};
const GRAIN_LABELS: Record<string, string> = {
  none: "Không ràng buộc", canh_dai: "Canh dài", canh_ngan: "Canh ngắn", song_song_gay: "Song song gáy",
};
const DON_GIA_KEM = 100_000; // đơn giá kẽm minh hoạ cho panel công thức (§9.5)

// ── UTILITY: PARSE UNIT SUFFIX FROM LABEL ─────────────────────────────────────────
function parseLabelAndSuffix(label: string): { cleanLabel: string; suffix: string | null } {
  const parenMatch = label.match(/\s*\(([^)]+)\)\s*$/);
  if (parenMatch) {
    return { cleanLabel: label.replace(parenMatch[0], "").trim(), suffix: parenMatch[1] };
  }
  const percentMatch = label.match(/\s*%\s*$/);
  if (percentMatch) {
    return { cleanLabel: label.replace(percentMatch[0], "").trim(), suffix: "%" };
  }
  return { cleanLabel: label, suffix: null };
}

// ── INLINE SEARCH ICON ────────────────────────────────────────────────────────────
const SearchIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="rc__search-icon">
    <circle cx="11" cy="11" r="8"/>
    <path d="m21 21-4.3-4.3"/>
  </svg>
);

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

  // Danh sách (bản ghi) là mặc định; click 1 dòng → mở editor 3 cột.
  const [view, setView] = useState<"list" | "editor">("list");
  const [q, setQ] = useState("");

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
      if (cur) { setConfig(pickConfig(cur)); setBench(benchForMode(cur.layout_mode)); }
      setSaveErr(null); setView("editor");
    }).catch(() => { /* noop */ });
  }, [token]);

  const newRule = () => {
    setSelectedId(null); setVersions([]); setViewVersionId(null);
    setMa(""); setTen(""); setMoTa(""); setConfig(DEFAULT_CONFIG); setSaveErr(null);
    setView("editor");
  };

  const backToList = () => { setView("list"); loadRules(); };

  const loadVersion = (vid: number) => {
    const v = versions.find((x) => x.id === vid);
    if (v) { setViewVersionId(vid); setConfig(pickConfig(v)); }
  };

  // --- debounced live preview (§9.3) — chỉ chạy khi đang ở editor ---
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (!token || view !== "editor") return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      binhBaiApi.preview(token, { config, bench })
        .then((p) => { setPreview(p); setPreviewErr(null); })
        .catch((e: Error) => { setPreview(null); setPreviewErr(e.message); });
    }, 150);
    return () => window.clearTimeout(timer.current);
  }, [token, config, bench, view]);

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
    try { await binhBaiApi.remove(token, selectedId!); backToList(); }
    catch (e) { setSaveErr((e as Error).message); }
  };

  const filteredRules = useMemo(() => {
    const kw = q.trim().toLowerCase();
    if (!kw) return rules;
    return rules.filter((r) => r.ma.toLowerCase().includes(kw) || r.ten.toLowerCase().includes(kw));
  }, [rules, q]);

  const money = useMemo(() => computeMoney(preview, bench), [preview, bench]);
  const mode = config.layout_mode;
  // Lỗi (thiếu số liệu / không vừa khổ) → ẩn khối tiền vì con số kẽm/giấy vô nghĩa lúc này.
  const previewHasError = !!previewErr || (preview?.warnings.some((w) => w.severity === "error") ?? false);

  if (view === "list") {
    return (
      <div className="rc qtbb">
        <header className="rc__head">
          <p className="rc__eyebrow">Cấu hình danh mục · quy tắc</p>
          <div className="rc__headrow">
            <h1 className="rc__title">Quy tắc bình bài</h1>
            <span className="rc__count">{rules.length}</span>
          </div>
          <p className="rc__sub">Quy định biên bản, chừa mép đuôi nhíp máy, và kiểu xếp tay sách/gang tờ in.</p>
        </header>

        <div className="rc__toolbar">
          <div className="rc__search-wrapper">
            <SearchIcon />
            <input className="rc__search" placeholder="Tìm mã / tên quy tắc…" value={q}
              onChange={(e) => setQ(e.target.value)} />
          </div>
          <div className="rc__spacer" />
          <Button variant="accent" onClick={newRule}>
            <span style={{ fontSize: "16px", marginRight: "4px", fontWeight: "bold" }}>+</span> Tạo quy tắc
          </Button>
        </div>

        <div className="rc__tablewrap">
          <table className="rc__table">
            <thead>
              <tr>
                <th style={{ width: "15%" }}>Mã</th>
                <th style={{ width: "35%" }}>Tên quy tắc</th>
                <th>Kiểu bình bài</th>
                <th>Phiên bản</th>
                <th>Trạng thái</th>
              </tr>
            </thead>
            <tbody>
              {filteredRules.length === 0 && (
                <tr><td colSpan={5} className="rc__msg">Chưa có quy tắc nào. Bấm “Tạo quy tắc”.</td></tr>
              )}
              {filteredRules.map((r) => (
                <tr key={r.id} className="rc__row" onClick={() => selectRule(r.id)}>
                  <td className="rc__mono"><span className="rc__code-badge">{r.ma}</span></td>
                  <td className="rc__name">{r.ten}</td>
                  <td>{r.current_version ? MODE_LABELS[r.current_version.layout_mode] : "—"}</td>
                  <td className="rc__mono">v{r.current_version?.version_no ?? 1}{r.version_count > 1 ? ` (${r.version_count})` : ""}</td>
                  <td>
                    <span className={`rc-pill ${r.trang_thai === "active" ? "rc-pill--on" : "rc-pill--off"}`}>
                      {r.trang_thai === "active" ? "Đang dùng" : "Tạm ngưng"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  return (
    <div className="rc qtbb">
      <header className="rc__head">
        <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "8px" }}>
          <Button variant="ghost" onClick={backToList}>← Danh sách</Button>
          <p className="rc__eyebrow" style={{ margin: 0 }}>Cấu hình danh mục · quy tắc bình bài</p>
        </div>
        <div className="rc__headrow">
          <h1 className="rc__title">{isNew ? "Quy tắc mới" : ten}</h1>
          {!isNew && <span className="rc__count">{ma}</span>}
        </div>
      </header>

      <div className="qtbb__topbar" style={{ marginBottom: "20px", background: "var(--canvas, #fbfaf5)", padding: "12px 20px", borderRadius: "12px", border: "1.5px solid var(--rule-soft, #e8e3d3)", display: "flex", alignItems: "center" }}>
        {!isNew && versions.length > 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span style={{ fontSize: "13px", fontWeight: 700, color: "var(--ash, #8a8676)" }}>Phiên bản cấu hình:</span>
            <div className="rc-input-wrapper" style={{ width: "200px" }}>
              <select className="rc-input" style={{ padding: "6px 12px" }} value={viewVersionId ?? ""} onChange={(e) => loadVersion(Number(e.target.value))}>
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>v{v.version_no}{v.is_current ? " (hiện hành)" : " (cũ, chỉ đọc)"}</option>
                ))}
              </select>
            </div>
          </div>
        )}
        <div style={{ display: "flex", gap: "8px", marginLeft: "auto" }}>
          <Button variant="primary" onClick={save} disabled={saving}>
            {isNew ? "Tạo quy tắc" : "Lưu → đẻ version mới"}
          </Button>
          {!isNew && <Button variant="ghost" onClick={removeRule}>Xoá</Button>}
        </div>
      </div>

      {saveErr && <div className="banner banner--error" style={{ marginBottom: "16px" }}>{saveErr}</div>}
      {viewingOld && <div className="banner" style={{ marginBottom: "16px" }}>Đang xem phiên bản cũ (chỉ đọc) — sửa & lưu sẽ đẻ phiên bản mới.</div>}

      <div className="qtbb__cols">
        {/* ZONE TRÁI — cấu hình (lưới thẻ, dùng chiều ngang) + Bảng thử (thẻ rộng) */}
        <div className="qtbb__formzone">
          <div className="qtbb__grid-2">
            <div className="qtbb__card">
              <Section title="Danh tính" desc="Tên gọi để nhận biết quy tắc. Mã không đổi sau khi tạo." />
              <div className="rc-grid" style={{ marginBottom: "14px" }}>
                <label className="rc-field">
                  <span className="rc-field__label">Mã quy tắc *</span>
                  <div className={`rc-input-wrapper${!isNew ? " rc-input-wrapper--ro" : ""}`}>
                    <input className="rc-input rc-mono" value={ma} disabled={!isNew}
                      onChange={(e) => setMa(e.target.value.toUpperCase())} placeholder="VD: BB-0001" />
                  </div>
                  {isNew && <span className="rc-field__hint">Viết hoa, không dấu. Không sửa được sau khi tạo.</span>}
                </label>
                <label className="rc-field">
                  <span className="rc-field__label">Tên hiển thị *</span>
                  <div className="rc-input-wrapper">
                    <input className="rc-input" value={ten} onChange={(e) => setTen(e.target.value)}
                      placeholder="VD: Ấn phẩm phẳng n-up" />
                  </div>
                </label>
              </div>
              <label className="rc-field">
                <span className="rc-field__label">Mô tả chi tiết</span>
                <div className="rc-input-wrapper">
                  <textarea className="rc-input" value={moTa} onChange={(e) => setMoTa(e.target.value)} rows={2}
                    placeholder="Ghi chú cách dùng (không bắt buộc)" />
                </div>
              </label>
            </div>

            <div className="qtbb__card">
              <Section title="Kiểu xếp bình bài" desc="Cách xếp con/tay/blank trên tờ in — chọn theo loại sản phẩm." />
              <label className="rc-field" style={{ marginBottom: "14px" }}>
                <span className="rc-field__label">Kiểu xếp mặc định</span>
                <div className="rc-input-wrapper">
                  <select className="rc-input" value={mode} onChange={(e) => {
                    const m = e.target.value as LayoutMode;
                    set("layout_mode", m);
                    setBench(benchForMode(m));   // nạp số mẫu hợp kiểu → preview chạy ngay
                  }}>
                    {(Object.keys(MODE_LABELS) as LayoutMode[]).map((m) => (
                      <option key={m} value={m}>{MODE_LABELS[m]}</option>
                    ))}
                  </select>
                </div>
                <span className="rc-field__hint">{MODE_HINT[mode]}</span>
              </label>

              {mode === "step_repeat" && (
                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  <p className="qtbb__group-label" style={{ margin: "4px 0 0" }}>Tùy chọn kiểu này</p>
                  <div className="rc-field rc-field--check" style={{ border: "1px solid var(--rule-soft, #e8e3d3)", borderRadius: "8px", padding: "10px 14px", background: "#fff" }}>
                    <span className="rc-field__label">Ghép tờ (gang-run)</span>
                    <label className="rc-switch">
                      <input type="checkbox" checked={config.allow_gang}
                        onChange={(e) => set("allow_gang", e.target.checked)} />
                      <span className="rc-switch__slider" />
                      <span className="rc-switch__label">{config.allow_gang ? "Bật" : "Tắt"}</span>
                    </label>
                  </div>
                  <span className="rc-field__hint" style={{ marginTop: -4 }}>Cờ chính sách — thuật toán ghép nhiều job thật chạy ở màn Báo giá, không tính trong quy tắc.</span>
                  <Num label="Khe tối thiểu khi ghép job (mm)" v={config.min_gutter_mm} on={(n) => set("min_gutter_mm", n)}
                    hint="Ngưỡng cảnh báo khi bật ghép job. Nên ≥ 2×bleed + mạch dao." />
                </div>
              )}
              {mode === "signature" && (
                <div className="rc-grid">
                  <label className="rc-field">
                    <span className="rc-field__label">Số trang mỗi tay</span>
                    <div className="rc-input-wrapper">
                      <select className="rc-input" value={config.pages_per_sig ?? ""}
                        onChange={(e) => set("pages_per_sig", e.target.value ? Number(e.target.value) : null)}>
                        <option value="">Tự động (theo khổ máy)</option>
                        {[4, 8, 16, 32].map((n) => <option key={n} value={n}>{n} trang</option>)}
                      </select>
                    </div>
                    <span className="rc-field__hint">Tay lớn hơn → ít tay hơn → ít kẽm.</span>
                  </label>
                  <label className="rc-field">
                    <span className="rc-field__label">Kiểu trở</span>
                    <div className="rc-input-wrapper">
                      <select className="rc-input" value={config.work_style}
                        onChange={(e) => set("work_style", e.target.value as VersionConfig["work_style"])}>
                        <option value="sheetwise">In trở khác (kẽm = tay × màu × 2)</option>
                        <option value="work_turn">Tự trở (kẽm = tay × màu)</option>
                      </select>
                    </div>
                    <span className="rc-field__hint">Dùng chung 1 bộ kẽm cho cả 2 mặt → tiết kiệm nửa tiền kẽm.</span>
                  </label>
                </div>
              )}
              {mode === "nesting" && (
                <div style={{ marginTop: "4px" }}>
                  <p className="qtbb__group-label" style={{ margin: "4px 0 0" }}>Tùy chọn kiểu này</p>
                  <Num label="Chừa khung thải (matrix, mm)" v={config.matrix_allowance_mm} on={(n) => set("matrix_allowance_mm", n)}
                    hint="Khoảng thải giữa các blank. Lớn hơn → ít blank/tờ." />
                </div>
              )}
            </div>
          </div>

          <div className="qtbb__card" style={{ marginTop: "0px" }}>
            <Section title="Hình học chung" desc="Các khoản chừa trên tờ in (nhíp lấy từ Máy in). Đều ảnh hưởng số con/tờ và tiền giấy." />
            <div className="rc-grid" style={{ marginBottom: "14px" }}>
              <Num label="Chừa tay kê (mm)" v={config.side_margin_mm} on={(n) => set("side_margin_mm", n)}
                hint="Chừa 2 mép hông. Lớn hơn → ít con/tờ → tốn giấy." />
              <Num label="Chừa đuôi giấy (mm)" v={config.tail_colorbar_mm} on={(n) => set("tail_colorbar_mm", n)}
                hint="Dải canh màu ở đuôi tờ. Lớn hơn → ít con/tờ hơn." />
              <Num label="Chừa xén giữa con (mm)" v={config.gutter_mm} on={(n) => set("gutter_mm", n)}
                hint="Khe hở giữa 2 con để xén rời. Lớn hơn → ít con/tờ hơn." />
              <Num label="Bleed mặc định (mm)" v={config.bleed_default_mm} on={(n) => set("bleed_default_mm", n)}
                hint="Tràn lề mặc định nếu sản phẩm không khai riêng." />
            </div>
            
            <div className="rc-grid" style={{ marginBottom: "14px", alignItems: "start" }}>
              <div className="rc-field rc-field--check" style={{ border: "1px solid var(--rule-soft, #e8e3d3)", borderRadius: "8px", padding: "10px 14px", background: "#fff", margin: 0, height: "42px" }}>
                <span className="rc-field__label" style={{ fontSize: "13px" }}>Cho phép xoay con 90°</span>
                <label className="rc-switch">
                  <input type="checkbox" checked={config.allow_rotate}
                    onChange={(e) => set("allow_rotate", e.target.checked)} />
                  <span className="rc-switch__slider" />
                  <span className="rc-switch__label" style={{ minWidth: "35px" }}>{config.allow_rotate ? "Bật" : "Tắt"}</span>
                </label>
              </div>

              <label className="rc-field">
                <span className="rc-field__label">Ràng buộc thớ giấy</span>
                <div className="rc-input-wrapper">
                  <select className="rc-input" value={config.grain_constraint}
                    onChange={(e) => set("grain_constraint", e.target.value as VersionConfig["grain_constraint"])}>
                    {Object.keys(GRAIN_LABELS).map((g) => <option key={g} value={g}>{GRAIN_LABELS[g]}</option>)}
                  </select>
                </div>
              </label>
            </div>
            <span className="rc-field__hint" style={{ display: "block", marginBottom: "14px", marginTop: "-10px" }}>Hướng thớ giấy không khớp → ít con hơn → tốn giấy.</span>

            {mode === "signature" && (
              <div style={{ marginTop: "20px", borderTop: "1.5px dashed var(--rule-soft, #e8e3d3)", paddingTop: "16px" }}>
                <Section title="Ngưỡng cảnh báo sách" desc="Chỉ áp dụng cho bình tay sách — chỉ hiện cảnh báo nhắc nhở ở tính giá, không chặn." />
                <div className="rc-grid">
                  <NumOpt label="Trang tối thiểu" v={config.min_pages} on={(n) => set("min_pages", n)}
                    hint="Cảnh báo khi sách quá mỏng (keo ≥ 40 trang)." />
                  <NumOpt label="Trang tối đa" v={config.max_pages} on={(n) => set("max_pages", n)}
                    hint="Cảnh báo khi vượt giới hạn (ghim ≤ 64 trang)." />
                  <NumOpt label="Gáy tối thiểu (mm)" v={config.min_spine_mm} on={(n) => set("min_spine_mm", n)}
                    hint="Cảnh báo gáy quá mỏng để đóng keo nhiệt." />
                </div>
              </div>
            )}
          </div>

          <div className="qtbb__card qtbb__bench">
            <Section title="Bảng thử nghiệm" desc="Nhập thông số mẫu thử để xem trước sơ đồ + tiền trực quan. KHÔNG lưu vào quy tắc." />
            <p className="qtbb__group-label">Sản phẩm mẫu thử</p>
            <div className="qtbb__benchgrid" style={{ marginBottom: "14px" }}>
              <Num label="Con: rộng (mm)" v={bench.rong_tp} on={(n) => setB("rong_tp", n)} />
              <Num label="Con: dài (mm)" v={bench.dai_tp} on={(n) => setB("dai_tp", n)} />
              {mode === "signature" && <NumOpt label="Tổng số trang" v={bench.so_trang} on={(n) => setB("so_trang", n)} />}
              {mode === "nesting" && <Num label="Blank: rộng (mm)" v={bench.blank_w ?? 0} on={(n) => setB("blank_w", n)}
                hint="Kích thước dieline." />}
              {mode === "nesting" && <Num label="Blank: dài (mm)" v={bench.blank_h ?? 0} on={(n) => setB("blank_h", n)} />}
            </div>
            <p className="qtbb__group-label">Giấy &amp; máy in thử</p>
            <div className="qtbb__benchgrid" style={{ marginBottom: "14px" }}>
              <Num label="Tờ nguyên: rộng (mm)" v={bench.rong_ng} on={(n) => setB("rong_ng", n)} />
              <Num label="Tờ nguyên: dài (mm)" v={bench.dai_ng} on={(n) => setB("dai_ng", n)} />
              <Num label="Định lượng (gsm)" v={bench.gsm} on={(n) => setB("gsm", n)} />
              <Num label="Giá giấy (đ/kg)" v={bench.gia_kg} on={(n) => setB("gia_kg", n)} />
              <Num label="Nhíp máy (mm)" v={bench.gripper_mm} on={(n) => setB("gripper_mm", n)} />
              <Num label="Khổ máy tối đa (mm)" v={bench.max_w} on={(n) => setB("max_w", n)} hint="0 = không giới hạn." />
            </div>
            <p className="qtbb__group-label">Đơn hàng thử</p>
            <div className="qtbb__benchgrid">
              <Num label="Số lượng in" v={bench.so_luong} on={(n) => setB("so_luong", n)} />
              <Num label="Số màu mặt trước" v={bench.so_mau_truoc} on={(n) => setB("so_mau_truoc", n)} />
              <Num label="Số màu mặt sau" v={bench.so_mau_sau} on={(n) => setB("so_mau_sau", n)} hint="0 = in 1 mặt." />
            </div>
          </div>
        </div>

        {/* ZONE PHẢI — kết quả (sticky): sơ đồ + công thức */}
        <aside className="qtbb__outputs">
          <div className="qtbb__card qtbb__preview">
            <h3>Sơ đồ tờ in (live)</h3>
            <BinhBaiPreview config={config} bench={bench} preview={preview} error={previewErr} />
          </div>
          <div className="qtbb__card qtbb__formula">
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
                {!previewHasError && (
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
                )}
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
          </div>
        </aside>
      </div>
    </div>
  );
}

// --- small helpers ---
function Section({ title, desc }: { title: string; desc?: string }) {
  return (
    <div className="qtbb__section-head" style={{ borderBottom: "1.5px solid var(--rule-soft, #e8e3d3)", margin: "0 0 16px 0", paddingBottom: "10px" }}>
      <h3 style={{ fontSize: "14.5px", fontWeight: 700, color: "var(--ink, #14130f)" }}>{title}</h3>
      {desc && <p className="qtbb__section-desc" style={{ marginTop: "4px" }}>{desc}</p>}
    </div>
  );
}
function Num({ label, v, on, hint }: { label: string; v: number; on: (n: number) => void; hint?: string }) {
  const { cleanLabel, suffix } = parseLabelAndSuffix(label);
  return (
    <label className="rc-field">
      <span className="rc-field__label">{cleanLabel}</span>
      <div className="rc-input-wrapper">
        <input className="rc-input rc-input--num" type="number" value={v}
          onChange={(e) => on(e.target.value === "" ? 0 : Number(e.target.value))} />
        {suffix && <span className="rc-input-suffix">{suffix}</span>}
      </div>
      {hint && <span className="rc-field__hint">{hint}</span>}
    </label>
  );
}
function NumOpt({ label, v, on, hint }: { label: string; v: number | null; on: (n: number | null) => void; hint?: string }) {
  const { cleanLabel, suffix } = parseLabelAndSuffix(label);
  return (
    <label className="rc-field">
      <span className="rc-field__label">{cleanLabel}</span>
      <div className="rc-input-wrapper">
        <input className="rc-input rc-input--num" type="number" value={v ?? ""} placeholder="—"
          onChange={(e) => on(e.target.value === "" ? null : Number(e.target.value))} />
        {suffix && <span className="rc-input-suffix">{suffix}</span>}
      </div>
      {hint && <span className="rc-field__hint">{hint}</span>}
    </label>
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
  return mode === "signature" ? "Tay" : mode === "nesting" ? "Blank" : "Con";
}
function fmt(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}
// Bộ số mẫu cho Bảng thử nghiệm theo từng kiểu xếp
function benchForMode(mode: LayoutMode): TestBench {
  if (mode === "signature")
    return { ...DEFAULT_BENCH, rong_tp: 160, dai_tp: 240, so_trang: 32, binding: "perfect",
      caliper_mm: 0.1, blank_w: null, blank_h: null, rong_ng: 650, dai_ng: 860, gsm: 100,
      so_luong: 2000, so_mau_truoc: 4, so_mau_sau: 4 };
  if (mode === "nesting")
    return { ...DEFAULT_BENCH, rong_tp: 250, dai_tp: 180, blank_w: 250, blank_h: 180,
      so_trang: null, rong_ng: 720, dai_ng: 1020, gsm: 300, so_luong: 5000,
      so_mau_truoc: 4, so_mau_sau: 0 };
  return { ...DEFAULT_BENCH };  // step_repeat: name card 90×53
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
