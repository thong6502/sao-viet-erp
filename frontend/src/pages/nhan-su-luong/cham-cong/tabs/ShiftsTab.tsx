// Tab Khai ca (tách từ pages/ChamCongPage.tsx).
import { useCallback, useEffect, useState } from "react";
import { api, type WorkShift } from "../../../../api/client";
import {
  Clock,
  Trash2,
  Edit3,
  Moon,
  Sun,
  Plus,
  Factory,
  Building2,
} from "lucide-react";
import { CollapsibleSection } from "../components/CollapsibleSection";
import { ShiftForm } from "../modals/ShiftForm";
import { buildShiftMeta } from "../shared/helpers";
import { ShiftPlanPanel } from "./ShiftPlanPanel";

// --- Tab: Khai ca (HR) ------------------------------------------------------

// ============================================================================
// Khai ca — 3 khối gập: A · Ca làm việc · B · Phân ca tháng · C · Ca mặc định
// ============================================================================

export function ShiftsTab({ token }: { token: string }) {
  const [items, setItems] = useState<WorkShift[] | null>(null);
  const [editing, setEditing] = useState<WorkShift | "new" | null>(null);
  const load = useCallback(() => {
    api.attendance
      .shifts(token)
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

  async function remove(id: number) {
    if (!window.confirm("Bạn có chắc chắn muốn xóa ca làm việc này?")) return;
    await api.attendance.deleteShift(token, id);
    load();
  }

  const shiftMeta = buildShiftMeta(items ?? []);
  const activeCount = (items ?? []).filter((s) => s.is_active).length;

  return (
    <div className="cc-sp-stack">
      <CollapsibleSection
        title="A · Ca làm việc"
        summary={
          items == null ? (
            "đang tải…"
          ) : (
            <>
              <span className="cc-sp-sum__txt">
                {items.length} ca
                {activeCount !== items.length
                  ? ` · ${activeCount} đang dùng`
                  : ""}
              </span>
              {[...items]
                .sort((a, b) => a.id - b.id)
                .map((s) => {
                  const m = shiftMeta.get(s.id);
                  return (
                    <span
                      key={s.id}
                      className={`cc-sp-chip cc-sp-chip--${m?.tone ?? "steel"} is-hand`}
                      title={m?.title}
                    >
                      {m?.code}
                    </span>
                  );
                })}
            </>
          )
        }
      >
        <div className="cc-toolbar">
          <button
            className="btn btn--primary"
            onClick={() => setEditing("new")}
          >
            <Plus size={14} /> Thêm ca làm việc
          </button>
        </div>

        <div className="cc-card-grid">
          {items?.map((s) => (
            <div
              key={s.id}
              className={`cc-shift-card ${s.is_overnight ? "cc-shift-card--overnight" : ""}`}
            >
              <div className="cc-shift-card-actions">
                <button
                  className="btn btn--ghost"
                  style={{ padding: "4px 6px", minWidth: "auto" }}
                  onClick={() => setEditing(s)}
                  title="Sửa ca"
                >
                  <Edit3 size={13} />
                </button>
                <button
                  className="btn btn--ghost ns-danger"
                  style={{ padding: "4px 6px", minWidth: "auto" }}
                  onClick={() => remove(s.id)}
                  title="Xóa ca"
                >
                  <Trash2 size={13} />
                </button>
              </div>

              <div className="cc-shift-card-header">
                <span className="cc-shift-name">{s.name}</span>
                <span
                  className={`cc-badge-pill ${s.is_active ? "cc-badge-pill--primary" : "cc-badge-pill--gray"}`}
                >
                  {s.is_active ? "Đang hoạt động" : "Đã tắt"}
                </span>
              </div>
              <div className="cc-shift-times">
                <Clock size={13} style={{ color: "var(--ash)" }} />
                <span>
                  {s.start_time} – {s.end_time}
                </span>
              </div>
              <div className="cc-shift-meta">
                <span className="cc-badge-pill cc-badge-pill--gray">
                  Dung sai trễ: {s.grace_minutes}′
                </span>
                {s.is_overnight ? (
                  <span className="cc-badge-pill cc-badge-pill--purple">
                    <Moon
                      size={10}
                      style={{
                        display: "inline",
                        verticalAlign: "middle",
                        marginRight: "2px",
                      }}
                    />{" "}
                    Qua đêm
                  </span>
                ) : (
                  <span className="cc-badge-pill cc-badge-pill--primary">
                    <Sun
                      size={10}
                      style={{
                        display: "inline",
                        verticalAlign: "middle",
                        marginRight: "2px",
                      }}
                    />{" "}
                    Ca ngày
                  </span>
                )}
                {s.ca_san_xuat ? (
                  <span className="cc-badge-pill cc-badge-pill--orange">
                    <Factory
                      size={10}
                      style={{
                        display: "inline",
                        verticalAlign: "middle",
                        marginRight: "2px",
                      }}
                    />{" "}
                    Dưới xưởng
                  </span>
                ) : (
                  <span className="cc-badge-pill cc-badge-pill--gray">
                    <Building2
                      size={10}
                      style={{
                        display: "inline",
                        verticalAlign: "middle",
                        marginRight: "2px",
                      }}
                    />{" "}
                    Văn phòng
                  </span>
                )}
              </div>
              {s.note && (
                <div
                  style={{
                    fontSize: "12px",
                    color: "var(--ash)",
                    marginTop: "8px",
                  }}
                >
                  Ghi chú: {s.note}
                </div>
              )}
            </div>
          ))}
          {items?.length === 0 && (
            <div className="ns__empty" style={{ gridColumn: "1/-1" }}>
              Chưa có ca làm việc nào được cấu hình.
            </div>
          )}
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        title="B · Phân ca tháng"
        defaultOpen
        summary={
          <span className="cc-sp-sum__txt">
            Lưới ngày × nhân viên · ô trống = kế thừa ca nền
          </span>
        }
      >
        <ShiftPlanPanel token={token} />
      </CollapsibleSection>

      {/* KHÔNG có khối "C · Lịch sử thay đổi ca" riêng (chủ 29/07/2026): lịch sử nằm TRONG
          drawer "Lịch sử ca" của từng người — bấm vào tên nhân viên trên lưới. Hai chỗ cùng
          kể chuyện đổi ca thì người dùng phải tự đoán chỗ nào là chỗ thật. */}
      {editing && (
        <ShiftForm
          token={token}
          shift={editing === "new" ? null : editing}
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
