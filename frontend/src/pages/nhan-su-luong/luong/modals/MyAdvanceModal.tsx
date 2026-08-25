// Modal nhân viên tự đề nghị tạm ứng (tách từ pages/LuongPage.tsx).
import { useMemo, useState } from "react";
import { api } from "../../../../api/client";
import { MonthPicker } from "../../../../components/MonthPicker";
import { curYm, errText, khoangKyUng, ymLabel } from "../shared/helpers";

export function MyAdvanceModal({
  token,
  kind,
  dot1Prefill,
  kyMinServer,
  onClose,
  onSaved,
}: {
  token: string;
  kind: "tam_ung" | "luong_dot_1";
  dot1Prefill: number;
  /** Mốc kỳ sớm nhất còn lập được, từ `/advances/me`. null ⇒ dùng mốc 12 tháng mặc định. */
  kyMinServer: string | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isDot1 = kind === "luong_dot_1";
  const [ym, setYm] = useState(curYm());
  // Phiếu đợt 1: điền sẵn theo "Lương trả 1 lần" trong hồ sơ (vẫn cho sửa).
  const [amount, setAmount] = useState(isDot1 ? dot1Prefill : 0);
  const [dateStr, setDateStr] = useState(() =>
    new Date().toISOString().slice(0, 10),
  );
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // KHÔNG gọi `GET /api/luong/periods` ở đây: đường đó đòi quyền `luong:read`, còn màn này chỉ
  // cần `luong:create` ⇒ nhân viên thường gọi vào là 403. Thay vào đó server trả kèm mốc
  // `ky_min_chon_duoc` trong `/advances/me` — cùng lối với `luong_dot_1`.
  //
  // Chủ chốt 18/08/2026: **kỳ đã chốt thì không cho chọn nữa**. Mốc server = tháng liền sau kỳ
  // khoá muộn nhất; lấy mốc MUỘN HƠN giữa nó và mốc 12 tháng để không nới lỏng chốt chống gõ
  // nhầm năm. So chuỗi `YYYY-MM` là đúng thứ tự thời gian nên không cần đổi sang Date.
  const kyRange = useMemo(() => {
    const base = khoangKyUng();
    const min = kyMinServer && kyMinServer > base.min ? kyMinServer : base.min;
    return { min, max: base.max };
  }, [kyMinServer]);
  // Lịch của trình duyệt đã làm mờ tháng ngoài `min`/`max`, nhưng gõ tay thì vẫn lọt ⇒ so lại.
  // So chuỗi `YYYY-MM` là đúng thứ tự thời gian nên không cần đổi sang Date.
  const kyNgoaiKhoang = ym < kyRange.min || ym > kyRange.max;

  async function save() {
    if (amount <= 0) {
      setErr("Nhập số tiền > 0.");
      return;
    }
    if (kyNgoaiKhoang) {
      setErr(
        `Kỳ lương chỉ chọn được từ ${ymLabel(kyRange.min)} đến ${ymLabel(kyRange.max)}.`,
      );
      return;
    }
    const [year, month] = ym.split("-").map(Number);
    setBusy(true);
    setErr(null);
    try {
      await api.luong.createMyAdvance(token, {
        period_year: year,
        period_month: month,
        advance_date: dateStr,
        amount,
        reason: reason || null,
        kind,
      });
      onSaved();
    } catch (e) {
      setErr(errText(e));
      setBusy(false);
    }
  }
  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>{isDot1 ? "Xin thanh toán lương đợt 1" : "Đề nghị tạm ứng"}</h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          {isDot1 && (
            <p className="cc-note">
              Số tiền điền sẵn theo <b>“Lương trả 1 lần”</b> trong hồ sơ của bạn
              — sửa được. Kế toán duyệt xong mới trừ, hiện thành dòng{" "}
              <b>“Thanh toán lương đợt 1”</b> trên phiếu lương.
              {dot1Prefill <= 0 && (
                <>
                  {" "}
                  Hồ sơ chưa khai mức này — nhập số bạn muốn ứng hoặc hỏi HCNS.
                </>
              )}
            </p>
          )}
          <div className="ns-grid">
            <label className="ns-field">
              <span className="ns-field__label">Kỳ lương</span>
              <MonthPicker
                value={ym}
                onChange={setYm}
                ariaLabel="Kỳ lương"
                min={kyRange.min}
                max={kyRange.max}
              />
              <span className="ns-field__hint">
                Tháng sẽ trừ lại khoản ứng này trên bảng lương — không nhất
                thiết là tháng của ngày ứng.
              </span>
              {kyNgoaiKhoang && (
                <span className="ns-field__hint ns-field__hint--err">
                  Chỉ chọn được kỳ từ {ymLabel(kyRange.min)} đến{" "}
                  {ymLabel(kyRange.max)}.
                </span>
              )}
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Ngày ứng</span>
              <input
                type="date"
                value={dateStr}
                onChange={(e) => setDateStr(e.target.value)}
              />
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Số tiền *</span>
              <input
                type="number"
                min={0}
                value={amount}
                onChange={(e) => setAmount(Number(e.target.value))}
              />
            </label>
          </div>
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Lý do</span>
            <input value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          <button
            className="btn btn--primary"
            onClick={save}
            disabled={busy || kyNgoaiKhoang}
            title={
              kyNgoaiKhoang
                ? `Kỳ lương chỉ chọn được từ ${ymLabel(kyRange.min)} đến ${ymLabel(kyRange.max)}.`
                : undefined
            }
          >
            {busy ? "Đang gửi…" : "Gửi đề nghị"}
          </button>
        </footer>
      </div>
    </div>
  );
}
