// Tính giá thành — calculator: chọn Loại SP · Máy · Giấy + số lượng/màu/khổ → gọi engine
// (/api/tinh-gia/preview) → breakdown giá vốn→giá bán. CHƯA nối Báo giá (chỉ tính).
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ApiError } from "../api/client";
import { crud, tinhGiaPreview, type Row, type TinhGiaResult } from "../api/rebuildCatalog";
import "./tinh-gia-v2.css";

const spApi = crud("/api/loai-san-pham");
const mayApi = crud("/api/may-thiet-bi");
const giayApi = crud("/api/vat-lieu-kho/giay");

const vnd = (v: unknown) => (v == null ? "—" : Number(v).toLocaleString("vi-VN"));

export function TinhGiaPage() {
  const { token } = useAuth();
  const [sps, setSps] = useState<Row[]>([]);
  const [mays, setMays] = useState<Row[]>([]);
  const [giays, setGiays] = useState<Row[]>([]);

  const [form, setForm] = useState({
    loai_san_pham_id: "", may_id: "", giay_id: "",
    so_luong: "10000", so_mau_truoc: "4", so_mau_sau: "4",
    rong_tp: "53", dai_tp: "90", bleed_mm: "2", chi_phi_khac: "150000",
    overhead_cty_pct: "15", kieu_lai: "markup_tren_von", he_so_lai_pct: "20",
    chiet_khau_pct: "0", don_toi_thieu: "0", vat_rate: "",
  });
  const [res, setRes] = useState<TinhGiaResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string, v: string) => setForm((p) => ({ ...p, [k]: v }));

  useEffect(() => {
    if (!token) return;
    spApi.list(token).then((r) => setSps(r.items)).catch(() => {});
    mayApi.list(token).then((r) => setMays(r.items.filter((m) => String(m.trang_thai) === "active"))).catch(() => {});
    giayApi.list(token).then((r) => setGiays(r.items)).catch(() => {});
  }, [token]);

  const compute = useCallback(async () => {
    if (!token) return;
    if (!form.may_id || !form.giay_id) { setErr("Chọn Máy + Giấy."); return; }
    setBusy(true); setErr(null);
    try {
      const num = (s: string) => (s === "" ? undefined : Number(s));
      const out = await tinhGiaPreview(token, {
        loai_san_pham_id: num(form.loai_san_pham_id) ?? null,
        may_id: Number(form.may_id), giay_id: Number(form.giay_id),
        so_luong: Number(form.so_luong), so_mau_truoc: Number(form.so_mau_truoc),
        so_mau_sau: Number(form.so_mau_sau), rong_tp: Number(form.rong_tp), dai_tp: Number(form.dai_tp),
        bleed_mm: num(form.bleed_mm), chi_phi_khac: num(form.chi_phi_khac) ?? 0,
        quote: {
          overhead_cty_pct: num(form.overhead_cty_pct) ?? 0, kieu_lai: form.kieu_lai,
          he_so_lai_pct: num(form.he_so_lai_pct) ?? 0, chiet_khau_pct: num(form.chiet_khau_pct) ?? 0,
          don_toi_thieu: num(form.don_toi_thieu) ?? 0, vat_rate: num(form.vat_rate) ?? null,
        },
      });
      setRes(out);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Tính giá thất bại.");
      setRes(null);
    } finally { setBusy(false); }
  }, [token, form]);

  const comp = res?.components?.[0] as Record<string, unknown> | undefined;
  const impo = comp?.imposition as Record<string, unknown> | undefined;
  const lines = useMemo(() => comp ? [
    ["Giấy", comp.tien_giay], ["Kẽm", comp.tien_kem], ["Mực", comp.tien_muc],
    ["In", comp.tien_in], ["Gia công", comp.tien_gia_cong],
  ] as [string, unknown][] : [], [comp]);

  return (
    <main className="tg2">
      <header className="tg2__head">
        <p className="tg2__eyebrow">Kinh doanh · engine mới</p>
        <h1 className="tg2__title">Tính giá thành</h1>
        <p className="tg2__sub">Chọn sản phẩm · máy · giấy → engine ráp giá vốn → giá bán (chưa nối Báo giá).</p>
      </header>

      <div className="tg2__grid">
        {/* Form */}
        <section className="tg2__form card">
          {err && <div className="banner banner--error">{err}</div>}
          <div className="tg2-sec">Sản phẩm</div>
          <label className="tg2-f"><span>Loại sản phẩm</span>
            <select value={form.loai_san_pham_id} onChange={(e) => set("loai_san_pham_id", e.target.value)}>
              <option value="">— tùy chọn (lấy rule + routing + VAT) —</option>
              {sps.map((s) => <option key={s.id} value={s.id}>{s.ma} · {s.ten}</option>)}
            </select>
          </label>
          <div className="tg2-row2">
            <label className="tg2-f"><span>Khổ TP rộng (mm) *</span>
              <input type="number" value={form.rong_tp} onChange={(e) => set("rong_tp", e.target.value)} /></label>
            <label className="tg2-f"><span>Khổ TP dài (mm) *</span>
              <input type="number" value={form.dai_tp} onChange={(e) => set("dai_tp", e.target.value)} /></label>
          </div>
          <div className="tg2-row2">
            <label className="tg2-f"><span>Số lượng *</span>
              <input type="number" value={form.so_luong} onChange={(e) => set("so_luong", e.target.value)} /></label>
            <label className="tg2-f"><span>Bleed (mm)</span>
              <input type="number" value={form.bleed_mm} onChange={(e) => set("bleed_mm", e.target.value)} /></label>
          </div>
          <div className="tg2-row2">
            <label className="tg2-f"><span>Số màu mặt trước</span>
              <input type="number" value={form.so_mau_truoc} onChange={(e) => set("so_mau_truoc", e.target.value)} /></label>
            <label className="tg2-f"><span>Số màu mặt sau</span>
              <input type="number" value={form.so_mau_sau} onChange={(e) => set("so_mau_sau", e.target.value)} /></label>
          </div>

          <div className="tg2-sec">Máy & Giấy</div>
          <label className="tg2-f"><span>Máy in *</span>
            <select value={form.may_id} onChange={(e) => set("may_id", e.target.value)}>
              <option value="">— chọn máy —</option>
              {mays.map((m) => <option key={m.id} value={m.id}>{m.ma} · {m.ten}</option>)}
            </select>
          </label>
          <label className="tg2-f"><span>Giấy nguyên *</span>
            <select value={form.giay_id} onChange={(e) => set("giay_id", e.target.value)}>
              <option value="">— chọn giấy —</option>
              {giays.map((g) => <option key={g.id} value={g.id}>{g.ma} · {g.ten}</option>)}
            </select>
          </label>

          <div className="tg2-sec">Thương mại</div>
          <div className="tg2-row2">
            <label className="tg2-f"><span>Overhead cty %</span>
              <input type="number" value={form.overhead_cty_pct} onChange={(e) => set("overhead_cty_pct", e.target.value)} /></label>
            <label className="tg2-f"><span>Chi phí khác (đ)</span>
              <input type="number" value={form.chi_phi_khac} onChange={(e) => set("chi_phi_khac", e.target.value)} /></label>
          </div>
          <div className="tg2-row2">
            <label className="tg2-f"><span>Kiểu lãi</span>
              <select value={form.kieu_lai} onChange={(e) => set("kieu_lai", e.target.value)}>
                <option value="markup_tren_von">Markup / vốn</option>
                <option value="margin_tren_gia_ban">Margin / giá bán</option>
              </select></label>
            <label className="tg2-f"><span>Hệ số lãi %</span>
              <input type="number" value={form.he_so_lai_pct} onChange={(e) => set("he_so_lai_pct", e.target.value)} /></label>
          </div>
          <div className="tg2-row2">
            <label className="tg2-f"><span>Chiết khấu %</span>
              <input type="number" value={form.chiet_khau_pct} onChange={(e) => set("chiet_khau_pct", e.target.value)} /></label>
            <label className="tg2-f"><span>VAT % (trống = theo SP)</span>
              <input type="number" value={form.vat_rate} onChange={(e) => set("vat_rate", e.target.value)} placeholder="8" /></label>
          </div>

          <Button variant="primary" loading={busy} onClick={compute} style={{ marginTop: 12, width: "100%" }}>
            Tính giá
          </Button>
        </section>

        {/* Kết quả */}
        <section className="tg2__result">
          {!res ? (
            <div className="tg2__empty card">Nhập thông số rồi bấm <strong>Tính giá</strong> để xem breakdown.</div>
          ) : (
            <>
              <div className="tg2__price card">
                <div className="tg2__price-label">Đơn giá bán (đã VAT {res.vat_rate}%)</div>
                <div className="tg2__price-big">{vnd(res.don_gia_ban)}<span>đ/cái</span></div>
                <div className="tg2__price-total">Tổng {vnd(res.gia_ban)}đ · {vnd(Number(form.so_luong))} cái{res.moq_applied ? " · đã nâng sàn MOQ" : ""}</div>
              </div>

              <div className="tg2__card card">
                <div className="tg2__cardhead">Giá vốn · 1 bộ phận {impo ? `(${vnd(impo.don_vi_per_to_in)} con/tờ · ${vnd(impo.so_kem)} kẽm · ${vnd(impo.so_to_nguyen)} tờ nguyên)` : ""}</div>
                <table className="tg2__tbl">
                  <tbody>
                    {lines.map(([k, v]) => (
                      <tr key={k}><td>{k}</td><td className="tg2__num">{vnd(v)}đ</td></tr>
                    ))}
                    {res.chi_phi_khac > 0 && <tr><td>Chế bản / khác</td><td className="tg2__num">{vnd(res.chi_phi_khac)}đ</td></tr>}
                    <tr className="tg2__sum"><td>Giá vốn</td><td className="tg2__num">{vnd(res.gia_von)}đ</td></tr>
                  </tbody>
                </table>
              </div>

              <div className="tg2__card card">
                <div className="tg2__cardhead">Lắp ráp báo giá</div>
                <table className="tg2__tbl">
                  <tbody>
                    <tr><td>Giá thành (+ overhead)</td><td className="tg2__num">{vnd(res.gia_thanh)}đ</td></tr>
                    <tr><td>Giá net (+ lãi − CK{res.moq_applied ? " · sàn MOQ" : ""})</td><td className="tg2__num">{vnd(res.gia_net)}đ</td></tr>
                    <tr><td>VAT {res.vat_rate}%</td><td className="tg2__num">{vnd(res.vat)}đ</td></tr>
                    <tr className="tg2__sum"><td>Giá bán</td><td className="tg2__num">{vnd(res.gia_ban)}đ</td></tr>
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
