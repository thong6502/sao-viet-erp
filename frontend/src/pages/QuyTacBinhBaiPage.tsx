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
import "./master-data.css";
import "./quy-tac-binh-bai.css";

const MODE_LABELS: Record<LayoutMode, string> = {
  step_repeat: "Xếp con (step & repeat)",
  signature: "Bình tay sách (signature)",
  nesting: "Dàn khuôn bao bì (nesting)",
  repeat_around: "Lặp theo trục (tem cuộn)",
};
const MODE_HINT: Record<LayoutMode, string> = {
  step_repeat: "Xếp nhiều con giống nhau — name card, tờ rơi, poster, tem rời.",
  signature: "Gấp tay sách — sách, catalogue, tạp chí nhiều trang.",
  nesting: "Dàn khuôn từ dieline — hộp giấy, bao bì.",
  repeat_around: "Lặp quanh trục — tem/nhãn in cuộn.",
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
      if (cur) setConfig(pickConfig(cur));
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

  if (view === "list") {
    return (
      <div className="md-page qtbb">
        <div className="md-page__head">
          <h1 className="md-page__title">Quy tắc bình bài</h1>
          <div className="qtbb__topbar">
            <input className="input" placeholder="Tìm mã / tên…" value={q}
              onChange={(e) => setQ(e.target.value)} />
            <button className="btn btn--primary" onClick={newRule}>+ Tạo quy tắc</button>
          </div>
        </div>
        <div className="card md-page__tablewrap">
          <table className="md-page__table">
            <thead>
              <tr>
                <th>Mã</th>
                <th>Tên</th>
                <th>Kiểu bình bài</th>
                <th>Version</th>
                <th>Trạng thái</th>
              </tr>
            </thead>
            <tbody>
              {filteredRules.length === 0 && (
                <tr><td colSpan={5} className="md-page__empty">Chưa có quy tắc nào. Bấm “Tạo quy tắc”.</td></tr>
              )}
              {filteredRules.map((r) => (
                <tr key={r.id} className="md-page__row--click" onClick={() => selectRule(r.id)}>
                  <td className="md-page__mono">{r.ma}</td>
                  <td>{r.ten}</td>
                  <td>{r.current_version ? MODE_LABELS[r.current_version.layout_mode] : "—"}</td>
                  <td className="md-page__mono">v{r.current_version?.version_no ?? 1}{r.version_count > 1 ? ` (${r.version_count})` : ""}</td>
                  <td>
                    <span className={`md-page__status-badge ${r.trang_thai === "active" ? "is-active" : "is-inactive"}`}>
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
    <div className="md-page qtbb">
      <div className="md-page__head">
        <div className="qtbb__head-left">
          <button className="btn btn--ghost" onClick={backToList}>← Danh sách</button>
          <h1 className="md-page__title">{isNew ? "Quy tắc mới" : `${ma} — ${ten}`}</h1>
        </div>
        <div className="qtbb__topbar">
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
        {/* ZONE TRÁI — cấu hình (lưới thẻ, dùng chiều ngang) + Bảng thử (thẻ rộng) */}
        <div className="qtbb__formzone">
          <div className="qtbb__config">
            <div className="qtbb__card">
              <Section title="Danh tính" desc="Tên gọi để nhận biết quy tắc. Mã không đổi sau khi tạo." />
              <div className="qtbb__fields">
                <label className="field"><span className="field__label">Mã quy tắc *</span>
                  <input className="input" value={ma} disabled={!isNew}
                    onChange={(e) => setMa(e.target.value.toUpperCase())} placeholder="VD: PHANG-NUP" />
                  {isNew && <span className="field__hint">Viết hoa, không dấu. Không sửa được sau khi tạo.</span>}</label>
                <label className="field"><span className="field__label">Tên hiển thị *</span>
                  <input className="input" value={ten} onChange={(e) => setTen(e.target.value)}
                    placeholder="VD: Ấn phẩm phẳng n-up" /></label>
              </div>
              <label className="field"><span className="field__label">Mô tả</span>
                <textarea className="input" value={moTa} onChange={(e) => setMoTa(e.target.value)} rows={2}
                  placeholder="Ghi chú cách dùng (không bắt buộc)" /></label>
            </div>

            <div className="qtbb__card">
              <Section title="Kiểu xếp bình bài" desc="Cách xếp con/tay/blank trên tờ in — chọn theo loại sản phẩm." />
              <label className="field"><span className="field__label">Kiểu xếp</span>
                <select className="input" value={mode} onChange={(e) => set("layout_mode", e.target.value as LayoutMode)}>
                  {(Object.keys(MODE_LABELS) as LayoutMode[]).map((m) => (
                    <option key={m} value={m}>{MODE_LABELS[m]}</option>
                  ))}
                </select>
                <span className="field__hint">{MODE_HINT[mode]}</span></label>

              {mode === "step_repeat" && (
                <>
                  <p className="qtbb__group-label">Tùy chọn kiểu này</p>
                  <label className="field field--check"><input type="checkbox" checked={config.allow_gang}
                    onChange={(e) => set("allow_gang", e.target.checked)} /> Cho ghép nhiều job chung 1 tờ (gang-run)</label>
                  <Num label="Khe tối thiểu khi ghép job (mm)" v={config.min_gutter_mm} on={(n) => set("min_gutter_mm", n)}
                    hint="Chỉ áp dụng khi bật ghép job. Nên ≥ 2×bleed + mạch dao." />
                </>
              )}
              {mode === "signature" && (
                <>
                  <p className="qtbb__group-label">Tùy chọn kiểu này</p>
                  <label className="field"><span className="field__label">Số trang mỗi tay</span>
                    <select className="input" value={config.pages_per_sig ?? ""}
                      onChange={(e) => set("pages_per_sig", e.target.value ? Number(e.target.value) : null)}>
                      <option value="">Tự động (theo khổ máy)</option>
                      {[4, 8, 16, 32].map((n) => <option key={n} value={n}>{n} trang</option>)}
                    </select>
                    <span className="field__hint">Tay lớn hơn → ít tay hơn → ít kẽm (nhưng cần máy lớn).</span></label>
                  <label className="field"><span className="field__label">Kiểu trở</span>
                    <select className="input" value={config.work_style}
                      onChange={(e) => set("work_style", e.target.value as VersionConfig["work_style"])}>
                      <option value="sheetwise">In trở khác (kẽm = tay × màu × 2)</option>
                      <option value="work_turn">Tự trở (kẽm = tay × màu)</option>
                    </select>
                    <span className="field__hint">Tự trở dùng chung 1 bộ kẽm cho cả 2 mặt → tiết kiệm nửa tiền kẽm.</span></label>
                </>
              )}
              {mode === "nesting" && (
                <>
                  <p className="qtbb__group-label">Tùy chọn kiểu này</p>
                  <label className="field"><span className="field__label">Phương pháp dàn</span>
                    <select className="input" value={config.nest_method}
                      onChange={(e) => set("nest_method", e.target.value as VersionConfig["nest_method"])}>
                      <option value="grid">Xếp lưới (đơn giản)</option>
                      <option value="true_shape">Nest hình thật (tiết kiệm hơn)</option>
                    </select></label>
                  <Num label="Chừa khung thải (matrix, mm)" v={config.matrix_allowance_mm} on={(n) => set("matrix_allowance_mm", n)}
                    hint="Khoảng thải giữa các blank. Lớn hơn → ít blank/tờ." />
                </>
              )}
              {mode === "repeat_around" && (
                <>
                  <p className="qtbb__group-label">Tùy chọn kiểu này</p>
                  <label className="field"><span className="field__label">Số làn ngang cuộn</span>
                    <input className="input" type="number" value={config.lanes ?? ""} placeholder="Tự động"
                      onChange={(e) => set("lanes", e.target.value ? Number(e.target.value) : null)} />
                    <span className="field__hint">Bỏ trống = tự tính theo khổ cuộn.</span></label>
                  <Num label="Khoảng cách giữa tem (mm)" v={config.gap_around_mm} on={(n) => set("gap_around_mm", n)} />
                </>
              )}
            </div>

            <div className="qtbb__card">
              <Section title="Hình học chung" desc="Các khoảng chừa trên tờ in — đều ảnh hưởng số con/tờ và tiền giấy." />
              <div className="qtbb__fields">
                <Num label="Lề hông (mm)" v={config.side_margin_mm} on={(n) => set("side_margin_mm", n)}
                  hint="Chừa 2 mép trái/phải. Lớn hơn → ít con/tờ → tốn giấy hơn." />
                <Num label="Thang màu đuôi (mm)" v={config.tail_colorbar_mm} on={(n) => set("tail_colorbar_mm", n)}
                  hint="Dải canh màu ở đuôi tờ. Lớn hơn → ít con/tờ hơn." />
                <Num label="Khoảng cách giữa con (mm)" v={config.gutter_mm} on={(n) => set("gutter_mm", n)}
                  hint="Khe hở giữa 2 con để xén. Lớn hơn → ít con/tờ hơn." />
                <Num label="Bleed tràn lề (mm)" v={config.bleed_default_mm} on={(n) => set("bleed_default_mm", n)}
                  hint="Tràn lề mặc định nếu sản phẩm không khai riêng." />
              </div>
              <label className="field field--check"><input type="checkbox" checked={config.allow_rotate}
                onChange={(e) => set("allow_rotate", e.target.checked)} /> Cho xoay con 90° (lấy chiều nhiều con hơn)</label>
              <label className="field"><span className="field__label">Ràng buộc thớ giấy</span>
                <select className="input" value={config.grain_constraint}
                  onChange={(e) => set("grain_constraint", e.target.value as VersionConfig["grain_constraint"])}>
                  {Object.keys(GRAIN_LABELS).map((g) => <option key={g} value={g}>{GRAIN_LABELS[g]}</option>)}
                </select>
                <span className="field__hint">Ép hướng theo thớ giấy. Ép hướng xấu → ít con hơn → tốn giấy.</span></label>
            </div>

            <div className="qtbb__card">
              <Section title="Ngưỡng cảnh báo" desc="Bỏ trống nếu không cần. Chỉ cảnh báo, không chặn." />
              <div className="qtbb__fields">
                <NumOpt label="Trang tối thiểu" v={config.min_pages} on={(n) => set("min_pages", n)}
                  hint="Cảnh báo khi sách quá mỏng (keo ≥ 40)." />
                <NumOpt label="Trang tối đa" v={config.max_pages} on={(n) => set("max_pages", n)}
                  hint="Cảnh báo khi vượt (ghim ≤ 64)." />
                <NumOpt label="Gáy tối thiểu (mm)" v={config.min_spine_mm} on={(n) => set("min_spine_mm", n)}
                  hint="Cảnh báo gáy quá mỏng để đóng keo." />
              </div>
            </div>
          </div>

          <div className="qtbb__card qtbb__bench">
            <Section title="Bảng thử" desc="Nhập bộ số mẫu để xem trước sơ đồ + tiền. KHÔNG lưu vào quy tắc." />
            <p className="qtbb__group-label">Sản phẩm mẫu</p>
            <div className="qtbb__benchgrid">
              <Num label="Con: rộng (mm)" v={bench.rong_tp} on={(n) => setB("rong_tp", n)} />
              <Num label="Con: dài (mm)" v={bench.dai_tp} on={(n) => setB("dai_tp", n)} />
              {mode === "signature" && <NumOpt label="Tổng số trang" v={bench.so_trang} on={(n) => setB("so_trang", n)} />}
              {mode === "nesting" && <Num label="Blank: rộng (mm)" v={bench.blank_w ?? 0} on={(n) => setB("blank_w", n)}
                hint="Kích thước tấm khai triển (dieline)." />}
              {mode === "nesting" && <Num label="Blank: dài (mm)" v={bench.blank_h ?? 0} on={(n) => setB("blank_h", n)} />}
            </div>
            <p className="qtbb__group-label">Giấy &amp; máy in</p>
            <div className="qtbb__benchgrid">
              <Num label="Tờ nguyên: rộng (mm)" v={bench.rong_ng} on={(n) => setB("rong_ng", n)} />
              <Num label="Tờ nguyên: dài (mm)" v={bench.dai_ng} on={(n) => setB("dai_ng", n)} />
              <Num label="Định lượng (gsm)" v={bench.gsm} on={(n) => setB("gsm", n)} />
              <Num label="Giá giấy (đ/kg)" v={bench.gia_kg} on={(n) => setB("gia_kg", n)} />
              <Num label="Nhíp máy (mm)" v={bench.gripper_mm} on={(n) => setB("gripper_mm", n)} />
              <Num label="Khổ máy tối đa (mm)" v={bench.max_w} on={(n) => setB("max_w", n)} hint="0 = không giới hạn." />
              {mode === "repeat_around" && <NumOpt label="Số răng trục" v={bench.teeth} on={(n) => setB("teeth", n)} />}
              {mode === "repeat_around" && <NumOpt label="Bước răng (mm)" v={bench.pitch_mm} on={(n) => setB("pitch_mm", n)} />}
            </div>
            <p className="qtbb__group-label">Đơn hàng mẫu</p>
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
          </div>
        </aside>
      </div>
    </div>
  );
}

// --- small helpers ---
function Section({ title, desc }: { title: string; desc?: string }) {
  return (
    <div className="qtbb__section-head">
      <h3>{title}</h3>
      {desc && <p className="qtbb__section-desc">{desc}</p>}
    </div>
  );
}
function Num({ label, v, on, hint }: { label: string; v: number; on: (n: number) => void; hint?: string }) {
  return (
    <label className="field"><span className="field__label">{label}</span>
      <input className="input" type="number" value={v}
        onChange={(e) => on(e.target.value === "" ? 0 : Number(e.target.value))} />
      {hint && <span className="field__hint">{hint}</span>}</label>
  );
}
function NumOpt({ label, v, on, hint }: { label: string; v: number | null; on: (n: number | null) => void; hint?: string }) {
  return (
    <label className="field"><span className="field__label">{label}</span>
      <input className="input" type="number" value={v ?? ""} placeholder="— (bỏ trống)"
        onChange={(e) => on(e.target.value === "" ? null : Number(e.target.value))} />
      {hint && <span className="field__hint">{hint}</span>}</label>
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
