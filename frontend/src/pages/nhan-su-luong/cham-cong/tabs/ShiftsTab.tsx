// Tab Khai ca (tách từ pages/ChamCongPage.tsx).
import { useCallback, useEffect, useState } from "react";
import { api, type WorkShift } from "../../../../api/client";
import {
  AlertTriangle,
  Building2,
  Clock,
  Coffee,
  Edit3,
  Factory,
  FileText,
  Moon,
  Plus,
  Sun,
  Trash2,
} from "lucide-react";
import { CollapsibleSection } from "../components/CollapsibleSection";
import { ShiftForm } from "../modals/ShiftForm";
import { buildShiftMeta, normalizeTime24 } from "../shared/helpers";
import { ShiftPlanPanel } from "./ShiftPlanPanel";

// --- Tab: Khai ca (HR) ------------------------------------------------------

// Helper tính giờ làm thực tế: (ra - vào) - nghỉ giữa ca trên trục phút ngày công (qua đêm +1440)
function computeWorkHours(s: WorkShift): { hours: number; text: string } | null {
  const startRaw = normalizeTime24(s.start_time);
  const endRaw = normalizeTime24(s.end_time);
  if (!startRaw || !endRaw) return null;
  const toMin = (t: string) => {
    const [h, m] = t.split(":").map(Number);
    return (h || 0) * 60 + (m || 0);
  };
  const start = toMin(startRaw);
  let end = toMin(endRaw);
  if (s.is_overnight) end += 1440;
  if (end <= start) return null;
  let nghi = 0;
  if (s.break_start_time && s.break_end_time) {
    const bs0 = normalizeTime24(s.break_start_time);
    const be0 = normalizeTime24(s.break_end_time);
    if (bs0 && be0) {
      let bs = toMin(bs0);
      let be = toMin(be0);
      if (s.is_overnight) {
        if (bs < start) bs += 1440;
        if (be < start) be += 1440;
      }
      bs = Math.max(bs, start);
      be = Math.min(be, end);
      if (be > bs) nghi = be - bs;
    }
  }
  const netMinutes = end - start - nghi;
  if (netMinutes <= 0) return null;
  const h = netMinutes / 60;
  const formatted = h % 1 === 0 ? `${h}.0` : `${Math.round(h * 10) / 10}`;
  return {
    hours: h,
    text: `${formatted} giờ công`,
  };
}

// ============================================================================
// Khai ca — 3 khối gập: A · Ca làm việc · B · Phân ca tháng · C · Ca mặc định
// ============================================================================

export function ShiftsTab({
  token,
  focusEmployeeId,
}: {
  token: string;
  /** Từ nút "Đặt ca nền" ở hồ sơ NV — lưới Phân ca tháng lọc sẵn + mở form ca nền cho người này. */
  focusEmployeeId?: number;
}) {
  const [items, setItems] = useState<WorkShift[] | null>(null);
  const [editing, setEditing] = useState<WorkShift | "new" | null>(null);
  const [deletingShift, setDeletingShift] = useState<WorkShift | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Mẫu số đang áp cho mọi ca (07/09/2026): form Khai ca so "giờ làm thực" với số này.
  const [chuan, setChuan] = useState<{ gio: number | null; khop: boolean }>({
    gio: null,
    khop: false,
  });

  const load = useCallback(() => {
    api.attendance
      .shifts(token)
      .then((r) => {
        setItems(r.items);
        setChuan({ gio: r.gio_cong_chuan ?? null, khop: !!r.ca_khop_gio_chuan });
      })
      .catch(() => setItems([]));
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function executeDelete() {
    if (!deletingShift) return;
    try {
      setDeleteBusy(true);
      setDeleteError(null);
      await api.attendance.deleteShift(token, deletingShift.id);
      setDeletingShift(null);
      load();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Lỗi khi xóa ca làm việc.");
    } finally {
      setDeleteBusy(false);
    }
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
          {items?.map((s) => {
            const m = shiftMeta.get(s.id);
            const workHours = computeWorkHours(s);

            return (
              <div
                key={s.id}
                className={`cc-shift-card-v3 ${!s.is_active ? "is-inactive" : ""}`}
              >
                {/* 1. Header: Icon Sun/Moon 16px cạnh Tên ca + Badges + Trạng thái */}
                <div className="cc-shift-card-header-v3">
                  <div className="cc-shift-header-main">
                    <div className="cc-shift-title-line">
                      <span
                        className={`cc-shift-icon-wrap ${
                          s.is_overnight ? "is-overnight" : "is-day"
                        }`}
                        title={s.is_overnight ? "Ca đêm" : "Ca ngày"}
                      >
                        {s.is_overnight ? <Moon size={16} /> : <Sun size={16} />}
                      </span>
                      <h4 className="cc-shift-name-v3" title={s.name}>
                        {s.name}
                      </h4>
                    </div>

                    <div className="cc-shift-meta-badges">
                      {s.ca_san_xuat ? (
                        <span className="cc-badge-pill cc-badge-pill--orange">
                          <Factory size={11} className="cc-badge-pill__icon" /> Dưới xưởng
                          {m?.code && <span className="cc-shift-meta-code"> · {m.code}</span>}
                        </span>
                      ) : (
                        <span className="cc-badge-pill cc-badge-pill--gray">
                          <Building2 size={11} className="cc-badge-pill__icon" /> Văn phòng
                          {m?.code && <span className="cc-shift-meta-code"> · {m.code}</span>}
                        </span>
                      )}
                      {s.is_overnight && (
                        <span
                          className="cc-badge-pill cc-badge-pill--purple"
                          title="Ca làm việc qua đêm (+1 ngày)"
                        >
                          <Moon size={11} className="cc-badge-pill__icon" /> Qua đêm
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="cc-shift-status-wrap">
                    <span
                      className={`cc-shift-status-pill ${
                        s.is_active ? "is-active" : "is-inactive"
                      }`}
                    >
                      <span
                        className={`cc-shift-status-dot ${
                          s.is_active ? "is-active" : "is-inactive"
                        }`}
                      />
                      {s.is_active ? "Đang dùng" : "Đã tắt"}
                    </span>
                  </div>
                </div>

                {/* 2. Khung giờ không bị gãy dòng: {start} → {end} và pill {workHours.text} */}
                <div className="cc-shift-time-bar">
                  <div className="cc-shift-time-left">
                    <Clock size={15} className="cc-shift-clock-icon" />
                    <span className="cc-shift-time-range cc-shift-num">
                      {s.start_time} <span className="cc-shift-time-arrow">→</span> {s.end_time}
                    </span>
                  </div>
                  {workHours && (
                    <span
                      className="cc-shift-hours-pill"
                      title="Tổng giờ công thực tế sau khi trừ giờ nghỉ"
                    >
                      {workHours.text}
                    </span>
                  )}
                </div>

                {/* 3. Lịch trình: 2 cột gọn gàng, rõ ràng */}
                <div className="cc-shift-schedule-row">
                  <div className="cc-shift-schedule-col">
                    <Coffee size={13} className="cc-shift-col-icon" />
                    <span
                      className={`cc-shift-col-text ${
                        s.break_start_time && s.break_end_time ? "" : "is-muted"
                      }`}
                      title={
                        s.break_start_time && s.break_end_time
                          ? `Nghỉ giữa ca: ${s.break_start_time} – ${s.break_end_time}`
                          : "Ca không bố trí nghỉ giữa ca"
                      }
                    >
                      {s.break_start_time && s.break_end_time
                        ? `Nghỉ ${s.break_start_time} – ${s.break_end_time}`
                        : "Không nghỉ giữa ca"}
                    </span>
                  </div>
                  <div className="cc-shift-schedule-col cc-shift-schedule-col--right">
                    <Clock size={13} className="cc-shift-col-icon" />
                    <span className="cc-shift-col-text">
                      Dung sai trễ: <strong className="cc-shift-num">{s.grace_minutes}′</strong>
                    </span>
                  </div>
                </div>

                {/* 4. Hàng đãi ngộ: Cơm ca, Phụ cấp, và CHỈ hiện Hệ số đêm khi s.is_overnight === true */}
                <div className="cc-shift-perks">
                  <span className="cc-shift-perk">
                    <span className="cc-shift-perk__lbl">Cơm ca:</span>{" "}
                    <strong className="cc-shift-perk__val cc-shift-num">
                      {s.meal_allowance
                        ? `${s.meal_allowance.toLocaleString("vi-VN")} đ`
                        : "—"}
                    </strong>
                  </span>
                  <span className="cc-shift-perk__sep">·</span>
                  <span className="cc-shift-perk">
                    <span className="cc-shift-perk__lbl">Phụ cấp:</span>{" "}
                    <strong className="cc-shift-perk__val cc-shift-num">
                      {s.shift_allowance
                        ? `${s.shift_allowance.toLocaleString("vi-VN")} đ`
                        : "—"}
                    </strong>
                  </span>
                  {s.is_overnight && (
                    <>
                      <span className="cc-shift-perk__sep">·</span>
                      <span className="cc-shift-perk cc-shift-perk--night">
                        <span className="cc-shift-perk__lbl">Hệ số đêm:</span>{" "}
                        <strong className="cc-shift-perk__val cc-shift-num">
                          x{s.night_multiplier}
                        </strong>
                      </span>
                    </>
                  )}
                </div>

                {/* 5. Ghi chú (nếu có) */}
                {s.note && (
                  <div className="cc-shift-note-v3" title={s.note}>
                    <FileText size={12} className="cc-shift-note__icon" />
                    <span className="cc-shift-note__text">{s.note}</span>
                  </div>
                )}

                {/* 6. Footer thao tác gọn gàng, tinh tế */}
                <div className="cc-shift-card-foot-v3">
                  <button
                    type="button"
                    className="btn btn--outline cc-shift-btn-edit"
                    onClick={() => setEditing(s)}
                  >
                    <Edit3 size={13} /> Chỉnh sửa
                  </button>
                  <button
                    type="button"
                    className="btn btn--ghost ns-danger cc-shift-btn-del"
                    onClick={() => setDeletingShift(s)}
                    title="Xóa ca làm việc"
                  >
                    <Trash2 size={13} /> Xóa
                  </button>
                </div>
              </div>
            );
          })}
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
        <ShiftPlanPanel token={token} focusEmployeeId={focusEmployeeId} />
      </CollapsibleSection>

      {/* KHÔNG có khối "C · Lịch sử thay đổi ca" riêng (chủ 29/07/2026): lịch sử nằm TRONG
          drawer "Lịch sử ca" của từng người — bấm vào tên nhân viên trên lưới. Hai chỗ cùng
          kể chuyện đổi ca thì người dùng phải tự đoán chỗ nào là chỗ thật. */}
      {editing && (
        <ShiftForm
          token={token}
          gioCongChuan={chuan.gio}
          caKhopGioChuan={chuan.khop}
          shift={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}

      {/* Modal Xác nhận xóa ca làm việc chuẩn ERP */}
      {deletingShift && (
        <div
          className="ns-modal"
          role="dialog"
          aria-modal="true"
          onClick={() => !deleteBusy && setDeletingShift(null)}
        >
          <div
            className="ns-modal__box cc-delete-shift-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="ns-modal__head cc-del-modal__head">
              <div className="cc-del-modal__title-wrap">
                <div className="cc-del-modal__icon-badge">
                  <AlertTriangle size={18} />
                </div>
                <div>
                  <h2 className="cc-del-modal__title">Xác nhận xóa ca làm việc</h2>
                  <p className="cc-del-modal__sub">
                    Thao tác này sẽ gỡ bỏ cấu hình ca khỏi danh mục ca làm việc
                  </p>
                </div>
              </div>
              <button
                className="ns-modal__x"
                onClick={() => !deleteBusy && setDeletingShift(null)}
                aria-label="Đóng"
                disabled={deleteBusy}
              >
                ×
              </button>
            </header>

            <div className="ns-modal__body cc-del-modal__body">
              {deleteError && (
                <div className="banner banner--error" style={{ marginBottom: 12 }}>
                  <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: 2 }} />
                  <span>{deleteError}</span>
                </div>
              )}

              <div className="cc-del-modal__target-info">
                <div className="cc-del-modal__info-row">
                  <span className="cc-del-modal__info-label">Ca làm việc:</span>
                  <strong className="cc-del-modal__shift-name">{deletingShift.name}</strong>
                </div>
                <div className="cc-del-modal__info-row">
                  <span className="cc-del-modal__info-label">Khung giờ:</span>
                  <span className="cc-shift-num">
                    {deletingShift.start_time} → {deletingShift.end_time}
                  </span>
                  {deletingShift.is_overnight && (
                    <span className="cc-badge-pill cc-badge-pill--purple" style={{ marginLeft: 6 }}>
                      Qua đêm (+1 ngày)
                    </span>
                  )}
                </div>
              </div>

              <div className="cc-del-modal__warning-box">
                <AlertTriangle size={16} className="cc-del-modal__warning-icon" />
                <div className="cc-del-modal__warning-text">
                  <strong>Cảnh báo phân công:</strong> Nếu ca này đã được phân công cho nhân viên trong bảng phân ca tháng hoặc có dữ liệu chấm công liên quan, việc xóa ca có thể ảnh hưởng đến kết quả tính công.
                </div>
              </div>
            </div>

            <footer className="ns-modal__foot cc-del-modal__foot">
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => {
                  setDeletingShift(null);
                  setDeleteError(null);
                }}
                disabled={deleteBusy}
              >
                Hủy bỏ
              </button>
              <button
                type="button"
                className="btn btn--danger"
                onClick={executeDelete}
                disabled={deleteBusy}
              >
                {deleteBusy ? "Đang xóa…" : "Xóa ca"}
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}
