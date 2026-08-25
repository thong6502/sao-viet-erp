// Form điểm chấm công (tách từ pages/ChamCongPage.tsx).
import { useState } from "react";
import {
  api,
  type WorkLocation,
  type WorkLocationInput,
} from "../../../../api/client";
import { Navigation } from "lucide-react";
import { getPosition, geoErrText } from "../shared/helpers";

export function LocationForm({
  token,
  location,
  onClose,
  onSaved,
}: {
  token: string;
  location: WorkLocation | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<WorkLocationInput>({
    name: location?.name ?? "",
    latitude: location?.latitude ?? 0,
    longitude: location?.longitude ?? 0,
    radius_m: location?.radius_m ?? 150,
    note: location?.note ?? "",
    is_active: location?.is_active ?? true,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);

  function set<K extends keyof WorkLocationInput>(
    k: K,
    v: WorkLocationInput[K],
  ) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function useMyLocation() {
    setLocating(true);
    setError(null);
    try {
      const pos = await getPosition();
      setForm((f) => ({
        ...f,
        latitude: Number(pos.coords.latitude.toFixed(7)),
        longitude: Number(pos.coords.longitude.toFixed(7)),
      }));
    } catch (e) {
      setError(geoErrText(e));
    } finally {
      setLocating(false);
    }
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      if (!form.name.trim()) throw new Error("Vui lòng nhập tên điểm chấm công.");
      if (location)
        await api.attendance.updateLocation(token, location.id, form);
      else await api.attendance.createLocation(token, form);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi lưu.");
      setBusy(false);
    }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box cc-day-detail-modal-box">
        <header className="ns-modal__head">
          <div className="cc-modal-title-group">
            <h2>{location ? "Chỉnh sửa điểm chấm công" : "Tạo điểm chấm công mới"}</h2>
            <p className="cc-modal-subtitle">Cấu hình tọa độ GPS và bán kính geofence cho phép chốt công</p>
          </div>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body cc-day-detail-modal-body">
          {error && <div className="banner banner--error cc-ts-msg-banner" style={{ marginBottom: 16 }}>{error}</div>}
          
          <label className="ns-field">
            <span className="cc-field-label">Tên điểm chấm công *</span>
            <input
              className="cc-input-text"
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder="vd: Xưởng in Sao Việt Nhật, Văn phòng đại diện..."
            />
          </label>

          <div style={{ marginTop: 12, marginBottom: 12 }}>
            <button
              type="button"
              className="btn btn--ghost"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                width: "100%",
                justifyContent: "center",
                borderStyle: "dashed",
                borderColor: "var(--rust)",
                color: "var(--rust-deep)",
                background: "var(--rust-soft)",
                padding: "8px 14px",
                borderRadius: "var(--r-3)",
                fontWeight: "var(--fw-bold)",
                fontSize: "12.5px"
              }}
              onClick={useMyLocation}
              disabled={locating}
            >
              <Navigation size={14} />
              <span>{locating ? "Đang lấy tọa độ GPS..." : "Lấy vị trí GPS hiện tại của tôi"}</span>
            </button>
          </div>

          <div className="ns-grid" style={{ marginTop: 12 }}>
            <label className="ns-field">
              <span className="cc-field-label">Vĩ độ (latitude)</span>
              <input
                type="number"
                step="0.0000001"
                className="cc-input-text"
                value={form.latitude}
                onChange={(e) => set("latitude", Number(e.target.value))}
              />
            </label>
            <label className="ns-field">
              <span className="cc-field-label">Kinh độ (longitude)</span>
              <input
                type="number"
                step="0.0000001"
                className="cc-input-text"
                value={form.longitude}
                onChange={(e) => set("longitude", Number(e.target.value))}
              />
            </label>
          </div>

          <label className="ns-field" style={{ marginTop: 14 }}>
            <span className="cc-field-label">Bán kính cho phép (mét) *</span>
            <input
              type="number"
              min={10}
              className="cc-input-text"
              value={form.radius_m}
              onChange={(e) => set("radius_m", Number(e.target.value))}
              placeholder="vd: 150"
            />
            <div className="cc-radius-presets-row" style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap", alignItems: "center" }}>
              <span style={{ fontSize: 11, color: "var(--ash-2)" }}>Chọn nhanh:</span>
              {[50, 100, 150, 200, 500].map((r) => (
                <button
                  key={r}
                  type="button"
                  className={`cc-calendar-chip ${form.radius_m === r ? "is-active" : ""}`}
                  style={{ padding: "2px 10px", fontSize: 11 }}
                  onClick={() => set("radius_m", r)}
                >
                  {r}m
                </button>
              ))}
            </div>
            <span className="cc-field-subtext" style={{ marginTop: 4 }}>Khoảng cách tối đa (mét) tính từ tâm vị trí cho phép nhân viên ấn nút Chấm công</span>
          </label>

          <label className="ns-field" style={{ marginTop: 14 }}>
            <span className="cc-field-label">Ghi chú</span>
            <input
              className="cc-input-text"
              value={form.note ?? ""}
              onChange={(e) => set("note", e.target.value)}
              placeholder="Địa chỉ cụ thể, hướng dẫn vị trí..."
            />
          </label>

          <div style={{ marginTop: 16, display: "flex", alignItems: "center", justifyContent: "space-between", background: "var(--canvas)", padding: "10px 14px", borderRadius: "var(--r-3)", border: "1px solid var(--rule-soft)" }}>
            <div>
              <span className="cc-field-label" style={{ margin: 0, fontWeight: "var(--fw-bold)" }}>Đang hoạt động</span>
              <span className="cc-field-subtext" style={{ display: "block" }}>Cho phép nhân viên chốt công tại vị trí này.</span>
            </div>
            <label className="cc-switch">
              <input
                type="checkbox"
                checked={!!form.is_active}
                onChange={(e) => set("is_active", e.target.checked)}
              />
              <span className="cc-slider" />
            </label>
          </div>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button className="btn btn--primary" onClick={save} disabled={busy}>
            {busy ? "Đang lưu…" : "Lưu cấu hình"}
          </button>
        </footer>
      </div>
    </div>
  );
}
