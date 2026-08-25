// Modal xin chỉnh công (tách từ pages/ChamCongPage.tsx).
import { useState } from "react";
import { api, type AdjustQuota } from "../../../../api/client";

// NV gửi yêu cầu chỉnh công cho 1 ngày (self-service).
export function RequestAdjustModal({
  token,
  date,
  quota,
  onClose,
  onSaved,
}: {
  token: string;
  date: string;
  quota: AdjustQuota | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [checkType, setCheckType] = useState<"in" | "out">("out");
  const [time, setTime] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Hạn mức đếm theo NGÀY CÔNG: ngày này đã có đơn còn hiệu lực thì gửi thêm (vd bù nốt lượt RA)
  // KHÔNG tốn lượt mới — phải nói ra, không thì người ta sợ không dám gửi.
  // Quota trả về là của THÁNG HIỆN TẠI, còn modal mở được cho ngày thuộc tháng khác (xem bảng
  // công tháng trước rồi bấm vào ô). Lệch tháng thì im lặng để backend quyết — thà không nhắc
  // còn hơn khoá nhầm nút Gửi bằng số của tháng khác.
  const sameMonth =
    !!quota &&
    date.startsWith(`${quota.year}-${String(quota.month).padStart(2, "0")}-`);
  const dayCounted = sameMonth && !!quota && quota.days.includes(date);
  const quotaBlocked =
    sameMonth &&
    !!quota &&
    quota.limit > 0 &&
    !dayCounted &&
    quota.used >= quota.limit;
  const quotaNote =
    !quota || quota.limit === 0 || !sameMonth
      ? null
      : quotaBlocked
        ? `Tháng ${quota.month} đã dùng hết ${quota.used}/${quota.limit} lần chỉnh công. ` +
          `Hủy một yêu cầu đang chờ, hoặc nhờ HCNS chấm bù trực tiếp.`
        : dayCounted
          ? `Ngày này đã tính lượt rồi — gửi thêm không tốn lượt. ` +
            `(Tháng ${quota.month}: đã dùng ${quota.used}/${quota.limit} ngày.)`
          : `Tháng ${quota.month}: đã dùng ${quota.used}/${quota.limit} ngày, còn ${quota.remaining} lần.`;

  async function submit() {
    if (!reason.trim()) {
      setError("Phải nhập lý do.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.attendance.createAdjustRequest(token, {
        date,
        check_type: checkType,
        suggested_time: time || null,
        reason: reason.trim(),
      });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi gửi yêu cầu.");
      setBusy(false);
    }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>Xin chỉnh công · {date}</h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {error && <div className="banner banner--error">{error}</div>}
          {quotaNote && (
            <div
              className={`banner ${quotaBlocked ? "banner--warn" : ""}`}
              style={{ marginBottom: 12 }}
            >
              {quotaNote}
            </div>
          )}
          <div className="ns-grid">
            <label className="ns-field">
              <span className="ns-field__label">Chấm còn thiếu</span>
              <select
                value={checkType}
                onChange={(e) => setCheckType(e.target.value as "in" | "out")}
              >
                <option value="in">VÀO</option>
                <option value="out">RA</option>
              </select>
            </label>
            <label className="ns-field">
              <span className="ns-field__label">
                Giờ (gợi ý, không bắt buộc)
              </span>
              <input
                type="time"
                value={time}
                onChange={(e) => setTime(e.target.value)}
              />
            </label>
          </div>
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Lý do (bắt buộc)</span>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="vd: Quên chấm ra vì máy hết pin…"
            />
          </label>
          <p className="cc-note">
            Yêu cầu sẽ gửi HCNS duyệt. Được duyệt thì công tự cập nhật.
          </p>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button
            className="btn btn--primary"
            onClick={submit}
            disabled={busy || quotaBlocked}
          >
            {busy ? "Đang gửi…" : "Gửi yêu cầu"}
          </button>
        </footer>
      </div>
    </div>
  );
}
