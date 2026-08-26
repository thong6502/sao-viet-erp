// Modal ghi phiếu tạm ứng cho nhân viên (tách từ pages/LuongPage.tsx).
import { useEffect, useMemo, useState } from "react";
import {
  api,
  type EmployeeRow,
  type PayrollPeriod,
} from "../../../../api/client";
import {
  errText,
  khoangKyUng,
  money,
  trangThaiKyUng,
  ymLabel,
} from "../shared/helpers";

export function AddAdvanceModal({
  token,
  emps,
  year,
  month,
  kind,
  onClose,
  onSaved,
}: {
  token: string;
  emps: EmployeeRow[];
  year: number;
  month: number;
  kind: "tam_ung" | "luong_dot_1";
  onClose: () => void;
  onSaved: () => void;
}) {
  const isDot1 = kind === "luong_dot_1";
  const [empId, setEmpId] = useState<number | "">("");
  const [amount, setAmount] = useState(0);
  const [dot1Profile, setDot1Profile] = useState<number | null>(null); // mức đợt 1 khai ở hồ sơ
  const [dateStr, setDateStr] = useState(() =>
    new Date().toISOString().slice(0, 10),
  );
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Danh sách kỳ lương, đọc MỘT LẦN lúc mở modal (không gọi lại theo từng lần đổi ô). `null` =
  // chưa biết: đang tải, hoặc gọi hỏng — im lặng chứ đừng đoán "kỳ chưa tạo".
  const [periods, setPeriods] = useState<PayrollPeriod[] | null>(null);
  const kyRange = useMemo(khoangKyUng, []);
  const ky = `${year}-${String(month).padStart(2, "0")}`;
  const kyNgoaiKhoang = ky < kyRange.min || ky > kyRange.max;
  // Kỳ có trong danh sách thì lấy trạng thái của nó; không có = chưa ai tính lương tháng đó.
  const kyStatus = useMemo(() => {
    if (periods === null) return null;
    const p = periods.find((x) => x.year === year && x.month === month);
    return p ? p.status : "chua_tao";
  }, [periods, year, month]);
  const kyNote = trangThaiKyUng(kyStatus);
  // Chốt chặn thật vẫn ở backend (409 kèm câu giải thích). Khoá nút ở đây chỉ để người lập biết
  // NGAY lúc mở modal, khỏi điền hết form rồi mới ăn lỗi.
  const kyChanGui =
    kyNgoaiKhoang || kyStatus === "locked" || kyStatus === "paid";

  useEffect(() => {
    let alive = true;
    api.luong
      .periods(token)
      .then((r) => {
        if (alive) setPeriods(r.items);
      })
      .catch(() => {
        // Không đọc được (mất mạng / thiếu ô Xem lương) ⇒ giữ `null`: không chip, không khoá nút.
        if (alive) setPeriods(null);
      });
    return () => {
      alive = false;
    };
  }, [token]);

  // Phiếu đợt 1: chọn NV xong tự điền sẵn số tiền = "Lương trả 1 lần" trong hồ sơ (cho sửa).
  useEffect(() => {
    if (!isDot1 || empId === "") {
      setDot1Profile(null);
      return;
    }
    let alive = true;
    api.luong
      .salaries(token, Number(empId))
      .then((r) => {
        if (!alive) return;
        const latest = r.items.length
          ? [...r.items].sort((a, b) =>
              b.effective_from.localeCompare(a.effective_from),
            )[0]
          : null;
        const d1 = latest?.luong_dot_1 ?? 0;
        setDot1Profile(d1);
        setAmount(d1);
      })
      .catch(() => {
        if (alive) setDot1Profile(null);
      });
    return () => {
      alive = false;
    };
  }, [isDot1, empId, token]);

  async function save() {
    if (empId === "" || amount <= 0) {
      setErr("Chọn nhân viên và nhập số tiền > 0.");
      return;
    }
    if (kyChanGui) {
      setErr(
        kyNgoaiKhoang
          ? `Kỳ ${ymLabel(ky)} nằm ngoài khoảng lập phiếu (${ymLabel(kyRange.min)} – ${ymLabel(kyRange.max)}).`
          : `Kỳ ${ymLabel(ky)} đã khoá — không lập được phiếu cho kỳ này.`,
      );
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api.luong.createAdvance(token, {
        employee_id: Number(empId),
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
          <h2>
            {isDot1 ? "Phiếu lương đợt 1" : "Thêm tạm ứng"} —{" "}
            {String(month).padStart(2, "0")}/{year}
          </h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          {isDot1 && (
            <p className="cc-note">
              Số tiền điền sẵn theo <b>“Lương trả 1 lần”</b> trong hồ sơ NV (sửa
              được). Duyệt phiếu xong mới trừ vào lương — hiện thành dòng{" "}
              <b>“Thanh toán lương đợt 1”</b> trên phiếu lương.
            </p>
          )}
          {/* Kỳ lương CHỈ ĐỌC: kỳ đi theo ô chọn tháng trên thanh công cụ (danh sách bên dưới
              cũng lọc theo nó) — bày thêm ô sửa ở đây thì lập xong phiếu lại không thấy nó trong
              bảng. Nhưng phải NÓI RA kỳ nào và kỳ đó đang ở trạng thái gì: đây là ô quyết định
              bảng lương tháng nào trừ lại khoản ứng. */}
          <div className="lg-ky-box">
            <div className="lg-ky-box__row">
              <span className="lg-ky-box__lbl">Kỳ lương</span>
              <span className="lg-ky-box__val">{ymLabel(ky)}</span>
            </div>
            <p className="lg-ky-box__hint">
              Tháng sẽ trừ lại khoản ứng này trên bảng lương — không nhất thiết
              là tháng của ngày ứng. Đổi kỳ ở ô chọn tháng trên thanh công cụ.
            </p>
            {kyNgoaiKhoang ? (
              <p className="lg-ky-status lg-ky-status--bad">
                Kỳ {ymLabel(ky)} nằm ngoài khoảng lập phiếu (
                {ymLabel(kyRange.min)} – {ymLabel(kyRange.max)}) — đổi kỳ trên
                thanh công cụ rồi lập lại.
              </p>
            ) : (
              kyNote && (
                <p className={`lg-ky-status lg-ky-status--${kyNote.tone}`}>
                  {kyNote.text}
                </p>
              )
            )}
          </div>
          <label className="ns-field">
            <span className="ns-field__label">Nhân viên *</span>
            <select
              value={empId}
              onChange={(e) =>
                setEmpId(e.target.value ? Number(e.target.value) : "")
              }
            >
              <option value="">— chọn —</option>
              {emps.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.code} · {e.full_name}
                </option>
              ))}
            </select>
          </label>
          <div className="ns-grid" style={{ marginTop: 12 }}>
            <label className="ns-field">
              <span className="ns-field__label">Số tiền *</span>
              <input
                type="number"
                min={0}
                value={amount}
                onChange={(e) => setAmount(Number(e.target.value))}
              />
              {isDot1 && empId !== "" && (
                <span className="cc-card__hint">
                  {dot1Profile && dot1Profile > 0
                    ? `Hồ sơ khai: ${money(dot1Profile)}đ`
                    : "Hồ sơ chưa khai 'Lương trả 1 lần' — nhập số tiền cần trả."}
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
          {/* Kỳ đã chốt / đã chi / ngoài khoảng ⇒ khoá nút ngay, khỏi điền hết form rồi mới ăn
              409. `title` để người dùng rê chuột biết vì sao nút xám. */}
          <button
            className="btn btn--primary"
            onClick={save}
            disabled={busy || kyChanGui}
            title={
              kyNgoaiKhoang
                ? `Kỳ ${ymLabel(ky)} nằm ngoài khoảng lập phiếu (${ymLabel(kyRange.min)} – ${ymLabel(kyRange.max)}).`
                : kyChanGui && kyNote
                  ? kyNote.text
                  : undefined
            }
          >
            {busy ? "Đang lưu…" : "Lưu"}
          </button>
        </footer>
      </div>
    </div>
  );
}
