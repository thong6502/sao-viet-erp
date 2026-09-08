// Form khai ca làm việc (tách từ pages/ChamCongPage.tsx).
// Nâng cấp UI/UX: Giao diện phẳng thuần (Flat Clean UI), loại bỏ các border hộp xám,
// phân nhóm bằng khoảng trắng & hairline thanh thoát, Quick Presets phẳng nhẹ,
// thanh đo giờ làm thực tế dạng inline, toggle switch dạng hàng cài đặt phẳng (Linear / Stripe style).
import { useState } from "react";
import {
  api,
  type WorkShift,
  type WorkShiftInput,
} from "../../../../api/client";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  Clock,
  Coffee,
  Factory,
  Moon,
  Sparkles,
} from "lucide-react";
import { TIME_HOURS, TIME_MINUTES } from "../shared/constants";
import { normalizeTime24 } from "../shared/helpers";

interface ShiftPreset {
  id: string;
  name: string;
  shortLabel: string;
  start_time: string;
  end_time: string;
  is_overnight: boolean;
  coNghi: boolean;
  break_start_time: string | null;
  break_end_time: string | null;
}

const SHIFT_PRESETS: ShiftPreset[] = [
  {
    id: "hc",
    name: "Hành chính",
    shortLabel: "Hành chính",
    start_time: "08:00",
    end_time: "17:00",
    is_overnight: false,
    coNghi: true,
    break_start_time: "12:00",
    break_end_time: "13:00",
  },
  {
    id: "ca1",
    name: "Ca 1 Sáng",
    shortLabel: "Ca 1",
    start_time: "06:00",
    end_time: "14:00",
    is_overnight: false,
    coNghi: false,
    break_start_time: null,
    break_end_time: null,
  },
  {
    id: "ca2",
    name: "Ca 2 Chiều",
    shortLabel: "Ca 2",
    start_time: "14:00",
    end_time: "22:00",
    is_overnight: false,
    coNghi: false,
    break_start_time: null,
    break_end_time: null,
  },
  {
    id: "ca3",
    name: "Ca 3 Đêm",
    shortLabel: "Ca 3 (Đêm)",
    start_time: "22:00",
    end_time: "06:00",
    is_overnight: true,
    coNghi: false,
    break_start_time: null,
    break_end_time: null,
  },
];

export function ShiftForm({
  token,
  shift,
  gioCongChuan = null,
  caKhopGioChuan = false,
  onClose,
  onSaved,
}: {
  token: string;
  shift: WorkShift | null;
  /** Giờ công chuẩn / ngày (Cấu hình lương) — hiện "giờ làm thực" so với số này. */
  gioCongChuan?: number | null;
  /** Luật "ca phải khớp giờ công chuẩn" đang bật ⇒ lệch là máy chủ từ chối lưu. */
  caKhopGioChuan?: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<WorkShiftInput>({
    name: shift?.name ?? "",
    start_time: shift?.start_time ?? "08:00",
    end_time: shift?.end_time ?? "17:00",
    is_overnight: shift?.is_overnight ?? false,
    night_multiplier: shift?.night_multiplier ?? 1.3,
    grace_minutes: shift?.grace_minutes ?? 5,
    break_start_time: shift?.break_start_time ?? null,
    break_end_time: shift?.break_end_time ?? null,
    meal_allowance: shift?.meal_allowance ?? 25000,
    shift_allowance: shift?.shift_allowance ?? 50000,
    note: shift?.note ?? "",
    is_active: shift?.is_active ?? true,
    ca_san_xuat: shift?.ca_san_xuat ?? true,
  });

  // Nghỉ giữa ca: tick là có, bỏ tick là gửi null cả hai — máy chủ đòi "cả hai hoặc không".
  const [coNghi, setCoNghi] = useState(
    !!shift?.break_start_time && !!shift?.break_end_time
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  type TimeField = "start_time" | "end_time" | "break_start_time" | "break_end_time";

  function set<K extends keyof WorkShiftInput>(k: K, v: WorkShiftInput[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  function timeParts(field: TimeField): [string, string] {
    const raw = (normalizeTime24(form[field] ?? "") ?? "00:00").split(":");
    return [raw[0] || "00", raw[1] || "00"];
  }

  function setTimePart(field: TimeField, part: "hour" | "minute", value: string) {
    const [hour, minute] = timeParts(field);
    set(field, part === "hour" ? `${value}:${minute}` : `${hour}:${value}`);
  }

  // Nếu ca hiện tại có phút lẻ (vd 07, 23...), tự động bổ sung vào options để không bao giờ mất giá trị cũ
  function getMinuteOptions(currentMinute: string) {
    if (!currentMinute || TIME_MINUTES.includes(currentMinute)) {
      return TIME_MINUTES;
    }
    return [...TIME_MINUTES, currentMinute].sort();
  }

  // Giờ làm THỰC = (ra − vào) − nghỉ giữa ca, trên trục phút ngày công (ca qua đêm +1440).
  function phutLamThuc(): number | null {
    const s = normalizeTime24(form.start_time);
    const e = normalizeTime24(form.end_time);
    if (!s || !e) return null;
    const toMin = (t: string) => {
      const [h, m] = t.split(":").map(Number);
      return h * 60 + m;
    };
    const start = toMin(s);
    let end = toMin(e);
    if (form.is_overnight) end += 1440;
    if (end <= start) return null;
    let nghi = 0;
    if (coNghi) {
      const bs0 = normalizeTime24(form.break_start_time ?? "");
      const be0 = normalizeTime24(form.break_end_time ?? "");
      if (bs0 && be0) {
        let bs = toMin(bs0);
        let be = toMin(be0);
        if (form.is_overnight) {
          if (bs < start) bs += 1440;
          if (be < start) be += 1440;
        }
        bs = Math.max(bs, start);
        be = Math.min(be, end);
        if (be > bs) nghi = be - bs;
      }
    }
    return end - start - nghi;
  }

  const gioText = (p: number) =>
    p % 60 ? `${Math.floor(p / 60)}h${String(p % 60).padStart(2, "0")}` : `${p / 60}h`;
  const phutThuc = phutLamThuc();
  const phutChuan = gioCongChuan != null ? Math.round(gioCongChuan * 60) : null;
  const lech = phutThuc != null && phutChuan != null && phutThuc !== phutChuan;

  function toggleNghi(on: boolean) {
    setCoNghi(on);
    setForm((f) => ({
      ...f,
      break_start_time: on ? (f.break_start_time ?? "12:00") : null,
      break_end_time: on ? (f.break_end_time ?? "13:00") : null,
    }));
  }

  function applyPreset(preset: ShiftPreset) {
    setCoNghi(preset.coNghi);
    setForm((f) => ({
      ...f,
      name: f.name ? f.name : preset.name,
      start_time: preset.start_time,
      end_time: preset.end_time,
      is_overnight: preset.is_overnight,
      break_start_time: preset.break_start_time,
      break_end_time: preset.break_end_time,
    }));
  }

  function isPresetActive(preset: ShiftPreset) {
    const sMatch = normalizeTime24(form.start_time) === preset.start_time;
    const eMatch = normalizeTime24(form.end_time) === preset.end_time;
    const oMatch = !!form.is_overnight === preset.is_overnight;
    const nMatch = coNghi === preset.coNghi;
    return sMatch && eMatch && oMatch && nMatch;
  }

  function TimeFieldPicker({
    field,
    label,
    icon,
  }: {
    field: TimeField;
    label: string;
    icon?: React.ReactNode;
  }) {
    const [hVal, mVal] = timeParts(field);
    const minuteOptions = getMinuteOptions(mVal);

    return (
      <div className="shift-time-picker">
        <label className="shift-time-header">
          {icon}
          <span>{label}</span>
        </label>
        <span className="cc-time-selects">
          <span className="cc-time-select">
            <span className="cc-time-select__caption">Giờ</span>
            <select
              aria-label={`Giờ ${label}`}
              value={hVal}
              onChange={(e) => setTimePart(field, "hour", e.target.value)}
            >
              {TIME_HOURS.map((hour) => (
                <option key={hour} value={hour}>
                  {hour}
                </option>
              ))}
            </select>
            <ChevronDown className="cc-time-select__chevron" size={13} />
          </span>
          <strong className="cc-time-selects__separator">:</strong>
          <span className="cc-time-select">
            <span className="cc-time-select__caption">Phút</span>
            <select
              aria-label={`Phút ${label}`}
              value={mVal}
              onChange={(e) => setTimePart(field, "minute", e.target.value)}
            >
              {minuteOptions.map((minute) => (
                <option key={minute} value={minute}>
                  {minute}
                </option>
              ))}
            </select>
            <ChevronDown className="cc-time-select__chevron" size={13} />
          </span>
        </span>
      </div>
    );
  }

  async function save() {
    setBusy(true);
    setError(null);
    const startTime = normalizeTime24(form.start_time);
    const endTime = normalizeTime24(form.end_time);
    if (!startTime || !endTime) {
      setError("Giờ ca không hợp lệ. Vui lòng chọn lại giờ và phút.");
      setBusy(false);
      return;
    }
    const breakStart = coNghi ? normalizeTime24(form.break_start_time ?? "") : null;
    const breakEnd = coNghi ? normalizeTime24(form.break_end_time ?? "") : null;
    if (coNghi && (!breakStart || !breakEnd)) {
      setError("Giờ nghỉ giữa ca không hợp lệ. Chọn đủ giờ bắt đầu và kết thúc.");
      setBusy(false);
      return;
    }
    const payload: WorkShiftInput = {
      ...form,
      start_time: startTime,
      end_time: endTime,
      break_start_time: breakStart,
      break_end_time: breakEnd,
    };
    setForm(payload);
    try {
      if (shift) await api.attendance.updateShift(token, shift.id, payload);
      else await api.attendance.createShift(token, payload);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi lưu ca làm việc.");
      setBusy(false);
    }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box ns-modal__box--shift">
        <header className="ns-modal__head">
          <div>
            <h2>{shift ? "Sửa ca làm việc" : "Thêm ca làm việc"}</h2>
            <p className="ns-modal__head-sub" style={{ margin: "2px 0 0", fontSize: "12px", color: "var(--ash)" }}>
              Khai báo khung giờ làm, giờ nghỉ và phụ cấp cho ca làm việc
            </p>
          </div>
          <button className="ns-modal__x" onClick={onClose} aria-label="Đóng">
            ×
          </button>
        </header>

        <div className="ns-modal__body shift-form-sections">
          {error && (
            <div className="banner banner--error" style={{ marginBottom: 4 }}>
              <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: 2 }} />
              <span>{error}</span>
            </div>
          )}

          {/* KHỐI 1: THÔNG TIN CƠ BẢN */}
          <section className="shift-section">
            <div className="shift-section__title">
              <span>1. Thông tin cơ bản</span>
            </div>

            <label className="ns-field">
              <span className="ns-field__label">
                Tên ca làm việc <span style={{ color: "var(--rust)" }}>*</span>
              </span>
              <input
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder="VD: Hành chính, Ca 1 Sáng, Ca 3 Đêm…"
                autoFocus
              />
            </label>

            <div className="shift-grid-2">
              <label className="ns-field">
                <span className="ns-field__label">Dung sai đi muộn</span>
                <div className="shift-input-unit">
                  <input
                    type="number"
                    min={0}
                    value={form.grace_minutes}
                    onChange={(e) => set("grace_minutes", Number(e.target.value))}
                  />
                  <span className="shift-input-unit__badge">phút</span>
                </div>
              </label>

              <div className="ns-field">
                <span className="ns-field__label">Trạng thái ca</span>
                <div
                  className={`shift-status-pill ${form.is_active ? "is-active" : ""}`}
                  onClick={() => set("is_active", !form.is_active)}
                  role="button"
                  tabIndex={0}
                >
                  <span className="shift-status-pill__indicator">
                    <span className="shift-status-pill__dot" />
                    {form.is_active ? "Đang sử dụng" : "Tạm ngưng"}
                  </span>
                  <span className="shift-switch">
                    <input
                      type="checkbox"
                      checked={!!form.is_active}
                      onChange={(e) => set("is_active", e.target.checked)}
                      onClick={(e) => e.stopPropagation()}
                    />
                    <span className="shift-switch__slider" />
                  </span>
                </div>
              </div>
            </div>
          </section>

          {/* KHỐI 2: KHUNG GIỜ & GIỜ NGHỈ (TRỌNG TÂM) */}
          <section className="shift-section shift-section--divided">
            <div className="shift-section__title">
              <span>2. Khung giờ & Giờ nghỉ giữa ca</span>
            </div>

            {/* Giờ vào ca và Giờ ra ca */}
            <div className="shift-time-range">
              <div className="shift-time-col">
                <TimeFieldPicker
                  field="start_time"
                  label="Giờ vào ca (24h)"
                  icon={<Clock size={13} style={{ color: "var(--rust)" }} />}
                />
              </div>

              <div className="shift-time-arrow" title="Chuyển tiếp giờ">
                <ArrowRight size={16} />
              </div>

              <div className="shift-time-col">
                <TimeFieldPicker
                  field="end_time"
                  label="Giờ ra ca (24h)"
                  icon={<Clock size={13} style={{ color: "var(--rust)" }} />}
                />
              </div>
            </div>

            {/* Quick Presets gợi ý nhanh phẳng nhẹ */}
            <div className="shift-presets">
              <span className="shift-presets__title">
                <Sparkles size={12} style={{ color: "var(--amber-deep)" }} />
                Gợi ý nhanh:
              </span>
              <div className="shift-presets__list">
                {SHIFT_PRESETS.map((p) => {
                  const active = isPresetActive(p);
                  return (
                    <button
                      key={p.id}
                      type="button"
                      className={`shift-preset-chip ${active ? "is-active" : ""}`}
                      onClick={() => applyPreset(p)}
                    >
                      <span>{p.shortLabel}</span>
                      <span className="shift-preset-chip__range">
                        ({p.start_time}-{p.end_time})
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Giờ làm thực tế: Dòng inline thanh thoát, KHÔNG đóng card viền */}
            <div className="shift-actual-inline">
              <span className="shift-actual-inline__lbl">Giờ làm thực tế:</span>
              <span className="shift-actual-inline__val">
                {phutThuc != null ? gioText(phutThuc) : "—"}
              </span>

              {phutChuan != null && phutThuc != null ? (
                <>
                  <span className="shift-actual-inline__sep">•</span>
                  {lech ? (
                    <span
                      className={`shift-actual-badge ${
                        caKhopGioChuan ? "shift-actual-badge--err" : "shift-actual-badge--warn"
                      }`}
                    >
                      <AlertTriangle size={12} />
                      Lệch chuẩn {gioText(phutChuan)}/ngày
                      {caKhopGioChuan ? " (Bắt buộc khớp)" : ""}
                    </span>
                  ) : (
                    <span className="shift-actual-badge shift-actual-badge--ok">
                      <CheckCircle2 size={12} />
                      Khớp chuẩn {gioText(phutChuan)}/ngày ✓
                    </span>
                  )}
                </>
              ) : null}
            </div>

            {/* Tùy chọn Có nghỉ giữa ca: Flat row (iOS / Linear style) */}
            <div
              className="shift-setting-row"
              onClick={() => toggleNghi(!coNghi)}
            >
              <div className="shift-setting-row__info">
                <div className="shift-setting-row__title">
                  <Coffee size={15} style={{ color: coNghi ? "var(--rust)" : "var(--ash-2)" }} />
                  <span>Có nghỉ giữa ca</span>
                </div>
                <div className="shift-setting-row__desc">
                  Nghỉ trưa, ăn ca — thời gian này không tính vào giờ làm việc
                </div>
              </div>
              <span className="shift-switch">
                <input
                  type="checkbox"
                  checked={coNghi}
                  onChange={(e) => toggleNghi(e.target.checked)}
                  onClick={(e) => e.stopPropagation()}
                />
                <span className="shift-switch__slider" />
              </span>
            </div>

            {/* Chọn giờ nghỉ khi bật: Mở rộng tự nhiên thụt lề 22px, không viền nét đứt */}
            {coNghi && (
              <div className="shift-nested-box">
                <div className="shift-time-range">
                  <div className="shift-time-col">
                    <TimeFieldPicker field="break_start_time" label="Nghỉ từ" />
                  </div>
                  <div className="shift-time-arrow">
                    <ArrowRight size={14} />
                  </div>
                  <div className="shift-time-col">
                    <TimeFieldPicker field="break_end_time" label="Nghỉ đến" />
                  </div>
                </div>
                <p className="shift-nested-note">
                  Ca qua đêm: Nếu giờ nghỉ nhỏ hơn giờ vào ca thì được tính là rạng sáng hôm sau.
                </p>
              </div>
            )}
          </section>

          {/* KHỐI 3: PHỤ CẤP & THIẾT LẬP */}
          <section className="shift-section shift-section--divided">
            <div className="shift-section__title">
              <span>3. Phụ cấp & Thiết lập</span>
            </div>

            <div className="shift-grid-2">
              <label className="ns-field">
                <span className="ns-field__label">Phụ cấp cơm</span>
                <div className="shift-input-unit">
                  <input
                    type="number"
                    min={0}
                    step={5000}
                    value={form.meal_allowance ?? 0}
                    onChange={(e) => set("meal_allowance", Number(e.target.value))}
                  />
                  <span className="shift-input-unit__badge">đ/ngày</span>
                </div>
              </label>

              <label className="ns-field">
                <span className="ns-field__label">Phụ cấp ca</span>
                <div className="shift-input-unit">
                  <input
                    type="number"
                    min={0}
                    step={5000}
                    value={form.shift_allowance ?? 0}
                    onChange={(e) => set("shift_allowance", Number(e.target.value))}
                  />
                  <span className="shift-input-unit__badge">đ/ca</span>
                </div>
              </label>
            </div>

            <div className="shift-settings-list">
              {/* Ca qua đêm: Flat row */}
              <div
                className="shift-setting-row"
                onClick={() => set("is_overnight", !form.is_overnight)}
              >
                <div className="shift-setting-row__info">
                  <div className="shift-setting-row__title">
                    <Moon size={15} style={{ color: form.is_overnight ? "var(--rust)" : "var(--ash-2)" }} />
                    <span>Ca qua đêm</span>
                  </div>
                  <div className="shift-setting-row__desc">
                    Bắt đầu hôm nay, kết thúc vào hôm sau (VD: 22:00 → 06:00)
                  </div>
                </div>
                <span className="shift-switch">
                  <input
                    type="checkbox"
                    checked={!!form.is_overnight}
                    onChange={(e) => set("is_overnight", e.target.checked)}
                    onClick={(e) => e.stopPropagation()}
                  />
                  <span className="shift-switch__slider" />
                </span>
              </div>

              {/* Hệ số ca đêm: Mở rộng tự nhiên phẳng bên dưới */}
              {form.is_overnight && (
                <div className="shift-nested-box">
                  <label className="ns-field">
                    <span className="ns-field__label">Hệ số ca đêm (theo luật ≥ 1.3 = +30%)</span>
                    <input
                      type="number"
                      min={1}
                      step={0.05}
                      value={form.night_multiplier ?? 1.3}
                      onChange={(e) => set("night_multiplier", Number(e.target.value))}
                    />
                  </label>
                  <p className="shift-nested-note">
                    Áp dụng cho giờ làm thực tế rơi vào khoảng 22h–06h trong ca. Tăng ca đêm tính riêng theo Cấu hình lương.
                  </p>
                </div>
              )}

              {/* Ca chạy máy xưởng sản xuất: Flat row */}
              <div
                className="shift-setting-row"
                onClick={() => set("ca_san_xuat", !form.ca_san_xuat)}
              >
                <div className="shift-setting-row__info">
                  <div className="shift-setting-row__title">
                    <Factory size={15} style={{ color: form.ca_san_xuat ? "var(--rust)" : "var(--ash-2)" }} />
                    <span>Ca chạy máy xưởng sản xuất</span>
                  </div>
                  <div className="shift-setting-row__desc">
                    Áp dụng cho người đứng máy: đưa vào khung giờ xếp lịch và tính % tải máy
                  </div>
                </div>
                <span className="shift-switch">
                  <input
                    type="checkbox"
                    checked={!!form.ca_san_xuat}
                    onChange={(e) => set("ca_san_xuat", e.target.checked)}
                    onClick={(e) => e.stopPropagation()}
                  />
                  <span className="shift-switch__slider" />
                </span>
              </div>
            </div>
          </section>
        </div>

        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>
            {busy ? "Đang lưu…" : "Lưu ca làm việc"}
          </button>
        </footer>
      </div>
    </div>
  );
}
