// Tab Điểm chấm công (tách từ pages/ChamCongPage.tsx).
import { useCallback, useEffect, useState } from "react";
import { api, type WorkLocation } from "../../../../api/client";
import {
  MapPin,
  CheckCircle,
  XCircle,
  Trash2,
  Edit3,
  Plus,
  Target,
  Navigation,
  ExternalLink,
} from "lucide-react";
import { EmptyState } from "../../../../components/EmptyState";
import { LocationForm } from "../modals/LocationForm";

// --- Tab: Điểm chấm công (HR) -----------------------------------------------

export function LocationsTab({ token }: { token: string }) {
  const [items, setItems] = useState<WorkLocation[] | null>(null);
  const [editing, setEditing] = useState<WorkLocation | "new" | null>(null);

  const load = useCallback(() => {
    api.attendance
      .locations(token)
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

  async function remove(id: number) {
    if (!window.confirm("Bạn có chắc chắn muốn xóa điểm chấm công này?"))
      return;
    await api.attendance.deleteLocation(token, id);
    load();
  }

  async function toggleActive(loc: WorkLocation) {
    try {
      await api.attendance.updateLocation(token, loc.id, {
        name: loc.name,
        latitude: loc.latitude,
        longitude: loc.longitude,
        radius_m: loc.radius_m,
        note: loc.note,
        is_active: !loc.is_active,
      });
      load();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Lỗi khi cập nhật.");
    }
  }

  const totalLocations = items?.length ?? 0;
  const activeLocations = items?.filter((l) => l.is_active).length ?? 0;
  const avgRadius =
    items && items.length > 0
      ? Math.round(items.reduce((acc, l) => acc + l.radius_m, 0) / items.length)
      : 0;

  return (
    <div className="cc-locations-wrapper">
      {/* 1. Header Toolbar & Quick Stats */}
      <div className="cc-calendar-dashboard" style={{ marginBottom: 20 }}>
        <div className="cc-calendar-stats-strip">
          <div className="cc-calendar-stat-card">
            <span className="cc-calendar-stat-icon cc-calendar-stat-icon--users">
              <MapPin size={16} />
            </span>
            <div className="cc-calendar-stat-info">
              <span className="cc-calendar-stat-val">{totalLocations}</span>
              <span className="cc-calendar-stat-label">Vị trí geofence</span>
            </div>
          </div>
          <div className="cc-calendar-stat-card">
            <span className="cc-calendar-stat-icon cc-calendar-stat-icon--check">
              <CheckCircle size={16} />
            </span>
            <div className="cc-calendar-stat-info">
              <span className="cc-calendar-stat-val">{activeLocations}</span>
              <span className="cc-calendar-stat-label">Đang hoạt động</span>
            </div>
          </div>
          <div className="cc-calendar-stat-card">
            <span className="cc-calendar-stat-icon cc-calendar-stat-icon--clock">
              <Target size={16} />
            </span>
            <div className="cc-calendar-stat-info">
              <span className="cc-calendar-stat-val">{avgRadius} m</span>
              <span className="cc-calendar-stat-label">Bán kính trung bình</span>
            </div>
          </div>
        </div>

        <button
          className="btn btn--primary cc-btn-cta-compact"
          onClick={() => setEditing("new")}
        >
          <Plus size={16} />
          <span>Thêm điểm chấm công</span>
        </button>
      </div>

      {/* 2. Location Cards Grid */}
      {items === null ? (
        <EmptyState trangThai="dang-tai" />
      ) : items.length === 0 ? (
        <EmptyState
          icon="building"
          title="Chưa khai điểm chấm công nào"
          sub='Bấm "+ Thêm điểm chấm công" để tạo điểm đầu tiên. Chưa có điểm thì nhân viên bấm ở đâu cũng được tính là ngoài vùng.'
        />
      ) : (
        <div className="cc-locations-grid">
          {items.map((l) => {
            const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${l.latitude},${l.longitude}`;
            return (
              <div
                key={l.id}
                className={`cc-loc-card-v2 ${!l.is_active ? "is-inactive" : ""}`}
              >
                <div className="cc-loc-card-head">
                  <div className="cc-loc-icon-wrapper">
                    <MapPin size={20} />
                  </div>
                  <div className="cc-loc-title-group">
                    <h3 className="cc-loc-card-title" title={l.name}>
                      {l.name}
                    </h3>
                    <div className="cc-loc-status-row">
                      {l.is_active ? (
                        <span className="cc-type-badge cc-type-badge--paid">
                          <CheckCircle size={11} />
                          <span>Đang dùng</span>
                        </span>
                      ) : (
                        <span className="cc-type-badge cc-type-badge--unpaid">
                          <XCircle size={11} />
                          <span>Đã tắt</span>
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="cc-leave-type-active-switch">
                    <label
                      className="cc-switch"
                      title={
                        l.is_active
                          ? "Đang sử dụng (Click để tắt)"
                          : "Đã tắt (Click để bật)"
                      }
                    >
                      <input
                        type="checkbox"
                        checked={l.is_active}
                        onChange={() => toggleActive(l)}
                      />
                      <span className="cc-slider" />
                    </label>
                  </div>
                </div>

                <div className="cc-loc-card-body">
                  <div className="cc-loc-coord-row">
                    <div className="cc-loc-coord-badge">
                      <Navigation size={12} style={{ opacity: 0.7 }} />
                      <span>
                        {Number(l.latitude).toFixed(6)},{" "}
                        {Number(l.longitude).toFixed(6)}
                      </span>
                    </div>

                    <a
                      href={mapsUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="cc-loc-maps-link"
                      title="Mở tọa độ trên Google Maps"
                    >
                      <span>Bản đồ</span>
                      <ExternalLink size={12} />
                    </a>
                  </div>

                  <div className="cc-geofence-radar-pill">
                    <div className="cc-geofence-pulse-ring" />
                    <Target size={13} style={{ color: "var(--rust)" }} />
                    <span>
                      Bán kính cho phép: <b>{l.radius_m} m</b>
                    </span>
                  </div>

                  {l.note && (
                    <div className="cc-loc-note-box" title={l.note}>
                      <span className="cc-loc-note-label">Ghi chú:</span> {l.note}
                    </div>
                  )}
                </div>

                <div className="cc-loc-card-foot">
                  <button
                    className="cc-leave-type-action-btn"
                    onClick={() => setEditing(l)}
                  >
                    <Edit3 size={13} />
                    <span>Sửa</span>
                  </button>
                  <button
                    className="cc-leave-type-action-btn cc-leave-type-action-btn--danger"
                    onClick={() => remove(l.id)}
                  >
                    <Trash2 size={13} />
                    <span>Xóa</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {editing && (
        <LocationForm
          token={token}
          location={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
    </div>
  );
}
