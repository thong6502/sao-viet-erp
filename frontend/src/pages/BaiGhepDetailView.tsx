// CHI TIẾT BÀI GHÉP — 4 tab (thông tin chung · thành viên · kiểm tương thích · giấy & số tờ) +
// cột phải checklist "Sẵn sàng xếp lịch". Số tờ/dư/% tờ dùng do server tính (dẫn xuất), FE chỉ hiển
// thị. Kiểm tương thích MỀM: hệ so + phân mức, người quyết. Nhắc thêm bước "xả tờ" ở từng LSX.
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ApiError,
  api,
  BAI_GHEP_CANH_BAO_LABELS,
  BAI_GHEP_MUC_META,
  BAI_GHEP_THIEU_LABELS,
  type BaiGhepDetail,
  type HangChoGhepItem,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { Icon } from "../components/Icons";
import { BangLoi, ChipGap, TrangThaiPill, classHan, ngay, num } from "./keHoachSxShared";

type TabKey = "chung" | "thanh-vien" | "tuong-thich" | "giay";
const TABS: { key: TabKey; label: string }[] = [
  { key: "chung", label: "Thông tin chung" },
  { key: "thanh-vien", label: "Thành viên" },
  { key: "tuong-thich", label: "Kiểm tương thích" },
  { key: "giay", label: "Giấy & số tờ" },
];

// Đọc kiểu in cho người: mã kỹ thuật → nhãn nghề (work-and-turn / work-and-tumble).
const QUY_CACH_IN_LABEL: Record<string, string> = {
  mot_mat: "1 mặt",
  "hai_mat(AB)": "2 mặt (AB)",
  tu_tro: "trở tự",
  tro_nhip: "trở nhíp",
};
const nhanCompat = (v: string | null) => (v == null ? "—" : QUY_CACH_IN_LABEL[v] ?? v);

interface Form {
  giay_id: number | null;
  kho_in_dai: number | null;
  kho_in_rong: number | null;
  hao_hut_setup: number;
  hao_hut_chay: number;
  ghi_chu: string;
}
const toForm = (d: BaiGhepDetail): Form => ({
  giay_id: d.giay_id,
  kho_in_dai: d.kho_in_dai,
  kho_in_rong: d.kho_in_rong,
  hao_hut_setup: d.hao_hut_setup,
  hao_hut_chay: d.hao_hut_chay,
  ghi_chu: d.ghi_chu ?? "",
});

export function BaiGhepDetailView({
  baiGhepId,
  onBack,
  onChanged,
}: {
  baiGhepId: number;
  onBack: () => void;
  onChanged?: () => void;
}) {
  const { token } = useAuth();
  const [d, setD] = useState<BaiGhepDetail | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [tab, setTab] = useState<TabKey>("chung");
  const [err, setErr] = useState<string | null>(null);
  const [readyErr, setReadyErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const apply = useCallback(
    (r: BaiGhepDetail) => {
      setD(r);
      setForm(toForm(r));
      onChanged?.();
    },
    [onChanged],
  );

  const load = useCallback(() => {
    if (!token) return;
    api.baiGhep
      .get(token, baiGhepId)
      .then((r) => {
        setD(r);
        setForm(toForm(r));
      })
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)));
  }, [token, baiGhepId]);

  useEffect(() => load(), [load]);

  const dirty = useMemo(() => {
    if (!d || !form) return false;
    return JSON.stringify(form) !== JSON.stringify(toForm(d));
  }, [d, form]);

  async function luu() {
    if (!token || !form) return;
    setSaving(true);
    setErr(null);
    try {
      apply(await api.baiGhep.update(token, baiGhepId, { ...form }));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function doiTrangThai(tt: "nhap" | "san_sang") {
    if (!token) return;
    setReadyErr(null);
    try {
      apply(await api.baiGhep.setTrangThai(token, baiGhepId, tt));
    } catch (e) {
      setReadyErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function suaUps(tvId: number, soCon: number) {
    if (!token) return;
    try {
      apply(await api.baiGhep.suaThanhVien(token, baiGhepId, tvId, soCon));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function boThanhVien(tvId: number) {
    if (!token) return;
    try {
      apply(await api.baiGhep.boThanhVien(token, baiGhepId, tvId));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function themThanhVien(lsxIds: number[]) {
    if (!token || !lsxIds.length) return;
    try {
      apply(await api.baiGhep.themThanhVien(token, baiGhepId, lsxIds));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function xoa() {
    if (!token || !d) return;
    if (!window.confirm(`Xoá bài ghép ${d.ma}? Các lệnh sẽ được trả về hàng chờ ghép.`)) return;
    try {
      await api.baiGhep.remove(token, baiGhepId);
      onChanged?.();
      onBack();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    }
  }

  if (err && !d) return <BangLoi text={err} onRetry={load} />;
  if (!d || !form) return <p className="khsx-muted">Đang tải…</p>;

  const giayOptions = Array.from(
    new Map(
      d.thanh_vien
        .filter((t) => t.giay_id != null)
        .map((t) => [t.giay_id as number, t.giay_ten] as [number, string | null]),
    ).entries(),
  );

  return (
    <div className="khsx-detail">
      <button type="button" className="khsx-back" onClick={onBack}>
        ‹ Danh sách bài ghép
      </button>
      <p className="eyebrow">Sản xuất · Bài ghép</p>
      <div className="khsx-detail__titlerow">
        <h1 className="khsx-detail__ma">{d.ma}</h1>
        <TrangThaiPill tt={d.trang_thai} lg />
        <span className="khsx__spacer" />
        <Button variant="ghost" onClick={xoa}>
          <Icon name="trash" size={14} /> Xoá
        </Button>
      </div>

      {err && <BangLoi text={err} onRetry={load} />}

      <div className="khsx-detail__grid">
        <div className="khsx-detail__main">
          <div className="khsx-tabs" role="tablist">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={tab === t.key}
                className={`khsx-tabs__btn ${tab === t.key ? "is-active" : ""}`}
                onClick={() => setTab(t.key)}
              >
                {t.label}
                {t.key === "thanh-vien" && <span className="chip-count">{d.thanh_vien.length}</span>}
              </button>
            ))}
          </div>

          {tab === "chung" && <TabChung d={d} form={form} setForm={setForm} />}
          {tab === "thanh-vien" && (
            <TabThanhVien d={d} onUps={suaUps} onBo={boThanhVien} onThem={themThanhVien} />
          )}
          {tab === "tuong-thich" && <TabTuongThich d={d} />}
          {tab === "giay" && (
            <TabGiay d={d} form={form} setForm={setForm} giayOptions={giayOptions} />
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
                  <Icon name="check" size={15} /> Sẵn sàng xếp lịch.
                </p>
                <Button variant="ghost" block onClick={() => doiTrangThai("nhap")}>
                  Mở lại để sửa
                </Button>
              </>
            ) : d.thieu.length ? (
              <>
                <p className="khsx-ready__title">Còn thiếu {d.thieu.length} mục</p>
                <ul className="khsx-ready__list" id="bghep-ready-list">
                  {d.thieu.map((code) => (
                    <li key={code} className="khsx-ready__item">
                      <Icon name="x" size={12} />
                      <span>{BAI_GHEP_THIEU_LABELS[code] ?? code}</span>
                      {(code === "thieu_giay" || code === "thieu_kho_in") && (
                        <button type="button" className="khsx-xlink" onClick={() => setTab("giay")}>
                          Sửa →
                        </button>
                      )}
                      {(code === "thieu_thanh_vien" || code === "thieu_ups" || code === "thieu_so_to") && (
                        <button type="button" className="khsx-xlink" onClick={() => setTab("thanh-vien")}>
                          Sửa →
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
                <Button variant="accent" block disabled aria-describedby="bghep-ready-list">
                  Sẵn sàng xếp lịch
                </Button>
              </>
            ) : (
              <>
                <p className="khsx-ready__title">
                  <Icon name="check" size={15} /> Đủ điều kiện.
                </p>
                <Button variant="accent" block onClick={() => doiTrangThai("san_sang")}>
                  Sẵn sàng xếp lịch
                </Button>
              </>
            )}
            {readyErr && <BangLoi text={readyErr} onRetry={() => setReadyErr(null)} />}
          </div>

          <div className="bghep-note">
            <Icon name="help" size={13} /> Nhớ thêm bước <strong>xả tờ</strong> ở từng lệnh khi in
            ghép — hệ không tự chèn.
          </div>

          {d.canh_bao.length > 0 && (
            <div className="khsx-luuy">
              <p className="khsx-luuy__title">
                <Icon name="help" size={14} /> Lưu ý ({d.canh_bao.length})
              </p>
              <ul className="khsx-luuy__list">
                {d.canh_bao.map((code) => (
                  <li key={code}>
                    <span>{BAI_GHEP_CANH_BAO_LABELS[code] ?? code}</span>
                  </li>
                ))}
              </ul>
              <p className="khsx-luuy__foot">Không chặn — bạn vẫn đánh dấu sẵn sàng được.</p>
            </div>
          )}

          <div className="khsx-facts">
            <Fact k="Số lệnh" v={num(d.thanh_vien.length)} />
            <Fact k="Số tờ tốt" v={num(d.so_to.so_to_tot)} />
            <Fact k="Tổng tờ cấp" v={num(d.so_to.tong_to)} />
            <Fact
              k="Tờ dùng"
              v={d.so_to.fill_pct == null ? "—" : `${d.so_to.fill_pct}%`}
              cls={
                d.so_to.fill_pct != null && (d.so_to.fill_pct < 55 || d.so_to.fill_pct > 100)
                  ? "khsx-date--soon"
                  : ""
              }
            />
            <Fact k="Hạn in gần nhất" v={ngay(d.so_to.han_in_muon_nhat)} cls={classHan(d.so_to.han_in_muon_nhat)} />
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
    </div>
  );
}

// --- Tab: thông tin chung ----------------------------------------------------
function TabChung({ d, form, setForm }: { d: BaiGhepDetail; form: Form; setForm: (f: Form) => void }) {
  return (
    <section className="khsx-panel">
      <div className="khsx-kvgrid">
        <KV k="Giấy chạy chung" v={d.giay_ten || <span className="khsx-muted">chưa chọn</span>} />
        <KV k="Khổ tờ in" v={d.kho_in_dai && d.kho_in_rong ? `${d.kho_in_dai}×${d.kho_in_rong} mm` : "—"} />
        <KV k="Số tờ tốt" v={num(d.so_to.so_to_tot)} />
        <KV k="Tổng tờ cấp" v={`${num(d.so_to.tong_to)} tờ`} />
      </div>
      <FillBar pct={d.so_to.fill_pct} />
      <label className="khsx-field">
        <span>Ghi chú</span>
        <textarea
          rows={3}
          value={form.ghi_chu}
          onChange={(e) => setForm({ ...form, ghi_chu: e.target.value })}
          placeholder="Ghi chú kế hoạch cho bài ghép…"
        />
      </label>
    </section>
  );
}

// --- Tab: thành viên ---------------------------------------------------------
function TabThanhVien({
  d,
  onUps,
  onBo,
  onThem,
}: {
  d: BaiGhepDetail;
  onUps: (tvId: number, soCon: number) => void;
  onBo: (tvId: number) => void;
  onThem: (lsxIds: number[]) => void;
}) {
  return (
    <section className="khsx-panel">
      <div className="khsx__tablewrap">
        <table className="khsx__table">
          <thead>
            <tr>
              <th>Lệnh</th>
              <th className="khsx-num">Số lượng</th>
              <th className="khsx-num">Con / tờ</th>
              <th className="khsx-num">Dự kiến</th>
              <th className="khsx-num">Dư</th>
              <th aria-label="Bỏ" />
            </tr>
          </thead>
          <tbody>
            {d.thanh_vien.map((t) => (
              <tr key={t.thanh_vien_id} className="khsx__row">
                <td>
                  <div className="khsx__code">{t.lsx_ma}</div>
                  <div className="khsx__name">
                    {t.lsx_ten || "—"} {t.is_rush && <ChipGap />}
                  </div>
                  {t.trang_thai_lsx && t.trang_thai_lsx !== "san_sang" && (
                    <span className="khsx-warn-inline">
                      <Icon name="help" size={11} /> không còn sẵn sàng
                    </span>
                  )}
                </td>
                <td className="khsx-num">
                  {num(t.so_luong_dat)} <span className="khsx-unit">{t.don_vi_tinh}</span>
                </td>
                <td className="khsx-num">
                  <input
                    type="number"
                    min={0}
                    className="bghep-ups"
                    defaultValue={t.so_con_tren_to}
                    onBlur={(e) => {
                      const v = Number(e.target.value);
                      if (v !== t.so_con_tren_to) onUps(t.thanh_vien_id, v);
                    }}
                    aria-label={`Số con trên tờ của ${t.lsx_ma}`}
                  />
                </td>
                <td className="khsx-num">{num(t.san_luong_du_kien)}</td>
                <td className={`khsx-num ${t.du > 0 ? "bghep-du" : ""}`}>{t.du > 0 ? `+${num(t.du)}` : num(t.du)}</td>
                <td>
                  <button
                    type="button"
                    className="khsx-xlink"
                    onClick={() => onBo(t.thanh_vien_id)}
                    title="Bỏ khỏi bài ghép"
                  >
                    Bỏ
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ThemPicker exclude={new Set(d.thanh_vien.map((t) => t.lsx_id))} onThem={onThem} />
    </section>
  );
}

function ThemPicker({ exclude, onThem }: { exclude: Set<number>; onThem: (ids: number[]) => void }) {
  const { token } = useAuth();
  const [open, setOpen] = useState(false);
  const [pool, setPool] = useState<HangChoGhepItem[] | null>(null);
  const [sel, setSel] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!open || !token) return;
    api.baiGhep.hangCho(token).then((r) => setPool(r.items.filter((i) => !exclude.has(i.lsx_id))));
  }, [open, token, exclude]);

  if (!open) {
    return (
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <Icon name="plus" size={14} /> Thêm lệnh vào bài
      </Button>
    );
  }
  return (
    <div className="bghep-pick">
      <p className="bghep-pick__title">Chọn lệnh sẵn sàng để thêm</p>
      {pool == null ? (
        <p className="khsx-muted">Đang tải…</p>
      ) : pool.length === 0 ? (
        <p className="khsx-muted">Không còn lệnh nào chờ ghép.</p>
      ) : (
        <ul className="bghep-pick__list">
          {pool.map((i) => (
            <li key={i.lsx_id}>
              <label>
                <input
                  type="checkbox"
                  checked={sel.has(i.lsx_id)}
                  onChange={() =>
                    setSel((s) => {
                      const n = new Set(s);
                      n.has(i.lsx_id) ? n.delete(i.lsx_id) : n.add(i.lsx_id);
                      return n;
                    })
                  }
                />
                <strong>{i.ma}</strong> · {i.ten} · {i.giay_ten || "—"} · {num(i.so_luong_dat)}
              </label>
            </li>
          ))}
        </ul>
      )}
      <div className="bghep-pick__foot">
        <Button variant="ghost" onClick={() => (setOpen(false), setSel(new Set()))}>
          Đóng
        </Button>
        <Button
          variant="accent"
          disabled={sel.size < 1}
          onClick={() => (onThem([...sel]), setOpen(false), setSel(new Set()))}
        >
          Thêm {sel.size > 0 ? `(${sel.size})` : ""}
        </Button>
      </div>
    </div>
  );
}

// --- Tab: kiểm tương thích ---------------------------------------------------
function TabTuongThich({ d }: { d: BaiGhepDetail }) {
  const members = d.thanh_vien;
  return (
    <section className="khsx-panel">
      <p className="bghep-hint">
        Hệ so khớp và phân mức — <strong>bạn quyết</strong>. Khác khổ thành phẩm là bình thường; chỉ
        cần các con lọt chung một tờ in.
      </p>
      <div className="khsx__tablewrap">
        <table className="khsx__table bghep-compat">
          <thead>
            <tr>
              <th>Thuộc tính</th>
              {members.map((m) => (
                <th key={m.thanh_vien_id}>{m.lsx_ma}</th>
              ))}
              <th>Kết quả</th>
            </tr>
          </thead>
          <tbody>
            {d.tuong_thich.rows.map((row) => {
              const meta = BAI_GHEP_MUC_META[row.muc] ?? { label: row.muc, tone: "warn" };
              return (
                <tr key={row.thuoc_tinh} className="khsx__row">
                  <td className="bghep-compat__attr">{row.thuoc_tinh}</td>
                  {row.gia_tri.map((v, i) => (
                    <td key={i}>{nhanCompat(v)}</td>
                  ))}
                  <td>
                    <span className={`bghep-muc bghep-muc--${meta.tone}`}>{meta.label}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// --- Tab: giấy & số tờ -------------------------------------------------------
function TabGiay({
  d,
  form,
  setForm,
  giayOptions,
}: {
  d: BaiGhepDetail;
  form: Form;
  setForm: (f: Form) => void;
  giayOptions: [number, string | null][];
}) {
  return (
    <section className="khsx-panel">
      <div className="khsx-form">
        <label className="khsx-field">
          <span>Giấy chạy chung</span>
          <select
            value={form.giay_id ?? ""}
            onChange={(e) => setForm({ ...form, giay_id: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">— chọn giấy —</option>
            {giayOptions.map(([id, ten]) => (
              <option key={id} value={id}>
                {ten || `Giấy #${id}`}
              </option>
            ))}
          </select>
        </label>
        <label className="khsx-field khsx-field--sm">
          <span>Khổ in dài (mm)</span>
          <input
            type="number"
            min={0}
            value={form.kho_in_dai ?? ""}
            onChange={(e) => setForm({ ...form, kho_in_dai: e.target.value ? Number(e.target.value) : null })}
          />
        </label>
        <label className="khsx-field khsx-field--sm">
          <span>Khổ in rộng (mm)</span>
          <input
            type="number"
            min={0}
            value={form.kho_in_rong ?? ""}
            onChange={(e) => setForm({ ...form, kho_in_rong: e.target.value ? Number(e.target.value) : null })}
          />
        </label>
        <label className="khsx-field khsx-field--sm">
          <span>Hao hụt canh máy (tờ)</span>
          <input
            type="number"
            min={0}
            value={form.hao_hut_setup}
            onChange={(e) => setForm({ ...form, hao_hut_setup: Number(e.target.value) })}
          />
        </label>
        <label className="khsx-field khsx-field--sm">
          <span>Hao hụt khi chạy (tờ)</span>
          <input
            type="number"
            min={0}
            value={form.hao_hut_chay}
            onChange={(e) => setForm({ ...form, hao_hut_chay: Number(e.target.value) })}
          />
        </label>
      </div>

      <div className="bghep-soto">
        <div className="bghep-soto__big">
          <span className="bghep-soto__num">{num(d.so_to.so_to_tot)}</span>
          <span className="bghep-soto__lbl">tờ tốt cần chạy</span>
        </div>
        <div className="bghep-soto__big">
          <span className="bghep-soto__num">{num(d.so_to.tong_to)}</span>
          <span className="bghep-soto__lbl">tổng tờ cấp (gồm hao)</span>
        </div>
      </div>
      <FillBar pct={d.so_to.fill_pct} />
    </section>
  );
}

// --- mảnh nhỏ ----------------------------------------------------------------
function FillBar({ pct }: { pct: number | null }) {
  if (pct == null) return null;
  const low = pct < 55;
  const over = pct > 100; // con không lọt chung 1 tờ — giảm số con/tờ cho vừa
  return (
    <div className="bghep-fill" title={`Diện tích tờ in được dùng ${pct}%`}>
      <div className="bghep-fill__label">
        Tờ dùng <strong>{pct}%</strong>
        {low && <span className="khsx-warn-inline"> · bài thưa, phí giấy</span>}
        {over && <span className="khsx-warn-inline"> · vượt tờ in — giảm số con/tờ</span>}
      </div>
      <div className="bghep-fill__track">
        <div
          className={`bghep-fill__bar ${low || over ? "is-low" : ""}`}
          style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
        />
      </div>
    </div>
  );
}

function KV({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="khsx-kv">
      <span className="khsx-kv__k">{k}</span>
      <span className="khsx-kv__v">{v}</span>
    </div>
  );
}

function Fact({ k, v, cls }: { k: string; v: ReactNode; cls?: string }) {
  return (
    <div className="khsx-fact">
      <span className="khsx-fact__k">{k}</span>
      <span className={`khsx-fact__v ${cls ?? ""}`}>{v}</span>
    </div>
  );
}
