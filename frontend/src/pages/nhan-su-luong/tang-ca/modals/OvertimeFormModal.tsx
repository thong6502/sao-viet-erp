// Modal gửi / tạo hộ phiếu tăng ca (tách từ pages/TangCaPage.tsx).
import { useEffect, useMemo, useState } from "react";
import {
  api,
  type EmployeeRow,
  type OvertimeRequest,
  type TranThangOut,
} from "../../../../api/client";
import { Button } from "../../../../components/Button";
import { fmtDateISO } from "../../../../utils/format";
import {
  EMPLOYEE_PICKER_SIZE,
  TRAN_NGUONG_VANG,
} from "../shared/constants";
import {
  errText,
  gioPhut,
  hhmmToMin,
  minToHhmm,
  plainHhmm,
  thangHomNay,
} from "../shared/helpers";

// --- Modal gửi / tạo hộ phiếu ------------------------------------------------

export function OvertimeFormModal({
  token,
  forEmployee,
  editing,
  onClose,
  onSaved,
}: {
  token: string;
  /** true = tổ trưởng tạo HỘ (chọn nhân viên, duyệt luôn); false = NV tự gửi. */
  forEmployee: boolean;
  /** Có = SỬA phiếu chờ duyệt (đổ sẵn dữ liệu, lưu bằng PUT). Không = tạo mới. */
  editing?: OvertimeRequest;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [emps, setEmps] = useState<EmployeeRow[]>([]);
  const [employeeId, setEmployeeId] = useState<number | null>(null);
  const [workDate, setWorkDate] = useState(editing?.work_date ?? "");
  const [from, setFrom] = useState(editing ? plainHhmm(editing.from_minute) : "22:00");
  const [to, setTo] = useState(editing ? plainHhmm(editing.to_minute) : "00:00");
  const [nextDay, setNextDay] = useState(editing ? editing.to_minute >= 1440 : true);
  const [reason, setReason] = useState(editing?.reason ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  /** Số dư TRẦN GIỜ LÀM THÊM THÁNG (Đ107). `null` = chưa nạp / gọi hỏng / chưa đủ dữ kiện để
   *  hỏi ⇒ ẩn khối, KHÔNG chặn — backend vẫn là chốt cuối. */
  const [tran, setTran] = useState<TranThangOut | null>(null);

  useEffect(() => {
    if (!forEmployee) return;
    api.employees
      .list(token, { size: EMPLOYEE_PICKER_SIZE })
      .then((r) => setEmps(r.items))
      .catch(() => setEmps([]));
  }, [forEmployee, token]);

  const fromMin = hhmmToMin(from);
  const toMin = hhmmToMin(to);
  const toAbs = toMin == null ? null : toMin + (nextDay ? 1440 : 0);
  const minutes = fromMin != null && toAbs != null ? toAbs - fromMin : null;

  // --- Trần giờ làm thêm THÁNG (Đ107) ---------------------------------------
  // Trần đếm theo THÁNG của NGÀY CÔNG, nên khoá nạp lại là "YYYY-MM" chứ không phải cả ngày:
  // đổi 05 → 12 trong cùng tháng thì số dư y hệt, gọi lại là phí một vòng mạng mỗi lần gõ.
  const thangKey = (workDate || thangHomNay()).slice(0, 7);
  useEffect(() => {
    // Tổ trưởng tạo hộ mà CHƯA chọn thợ: bỏ trống `employee_id` là backend trả số dư của CHÍNH
    // tổ trưởng — bày ra thì tổ trưởng đọc nhầm thành số của thợ rồi khai quá trần.
    if (forEmployee && employeeId == null) {
      setTran(null);
      return;
    }
    const [y, m] = thangKey.split("-").map(Number);
    if (!y || !m) {
      setTran(null);
      return;
    }
    let huy = false;
    api.overtime
      .tranThang(token, {
        year: y,
        month: m,
        employeeId: forEmployee ? employeeId : undefined,
        // Đang SỬA thì phiếu này KHÔNG được tự đếm chính nó, nếu không sửa 3h→4h lại báo
        // "đã dùng 3h" cộng thêm 4h nữa.
        excludeId: editing?.id,
      })
      .then((r) => !huy && setTran(r))
      .catch(() => !huy && setTran(null));
    return () => {
      huy = true;
    };
  }, [token, forEmployee, employeeId, thangKey, editing?.id]);

  /** Phút còn lại của tháng; `null` = công ty chưa bật trần ⇒ ẩn cả khối, không chặn gì. */
  const conLai =
    tran?.ap_tran && tran.con_lai_phut != null ? tran.con_lai_phut : null;
  const phieuNay = minutes != null && minutes > 0 ? minutes : 0;
  /** CHẶN CỨNG (chủ chốt 17/08/2026): hết trần thì lối duy nhất là vào Cấu hình lương nâng con
   *  số đó. KHÔNG có nút xin vượt, KHÔNG checkbox, KHÔNG ô lý do. */
  const vuotTran = conLai != null && (conLai <= 0 || phieuNay > conLai);
  /** Câu chặn của FE phải KHỚP Ý câu 400 backend trả (`_validate_window`) — hai câu khác nhau
   *  cho cùng một lỗi là cách nhanh nhất làm người dùng mất niềm tin vào con số. */
  const loiTran = useMemo(() => {
    if (!vuotTran || tran == null || conLai == null) return null;
    const [y, m] = thangKey.split("-");
    const thang = `${m}/${y}`;
    const daDung = gioPhut(tran.da_dung_phut);
    const tranStr = gioPhut(tran.tran_phut);
    if (conLai <= 0) {
      return `Tháng ${thang} đã dùng hết trần tăng ca (${daDung}/${tranStr}). Không cấp thêm phiếu được.`;
    }
    const sua =
      fromMin == null
        ? ""
        : ` Sửa giờ kết thúc còn tối đa ${minToHhmm(fromMin + conLai)}.`;
    return (
      `Vượt trần tăng ca tháng ${thang}. Đã đăng ký ${daDung}/${tranStr} — còn ` +
      `${gioPhut(conLai)} (gồm cả phiếu chờ duyệt). Phiếu này ${gioPhut(phieuNay)}.${sua}`
    );
  }, [vuotTran, tran, conLai, thangKey, fromMin, phieuNay]);

  async function save() {
    setErr(null);
    if (!workDate) return setErr("Cần chọn ngày công.");
    if (fromMin == null || toAbs == null) return setErr("Giờ phải dạng HH:MM.");
    if (minutes == null || minutes <= 0)
      return setErr(
        "Giờ kết thúc phải sau giờ bắt đầu (nếu qua nửa đêm nhớ tích “sang hôm sau”).",
      );
    if (forEmployee && employeeId == null) return setErr("Cần chọn nhân viên.");
    // Chốt cuối vẫn là backend (`_validate_window`) — chỗ này chỉ để phím Enter / gọi lại không
    // lách được cái nút đã tắt.
    if (loiTran) return setErr(loiTran);
    setBusy(true);
    try {
      const input = {
        work_date: workDate,
        from_minute: fromMin,
        to_minute: toAbs,
        reason: reason.trim() || null,
      };
      if (editing) {
        await api.overtime.updateMine(token, editing.id, input);
      } else if (forEmployee) {
        await api.overtime.createFor(token, {
          ...input,
          employee_id: employeeId as number,
        });
      } else {
        await api.overtime.createMine(token, input);
      }
      onSaved();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ns-modal" role="dialog" aria-modal="true">
      <div className="ns-modal__box">
        <header className="ns-modal__head">
          <h2>
            {editing
              ? "Sửa phiếu tăng ca"
              : forEmployee
                ? "Tạo phiếu tăng ca cho thợ"
                : "Gửi phiếu tăng ca"}
          </h2>
          <button className="ns-modal__x" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="ns-modal__body">
          {err && <div className="banner banner--error">{err}</div>}
          <div className="tc-note">
            <span>
              Khai <b>khoảng được phép tăng ca</b>. Tiền trả theo{" "}
              <b>giờ bấm ra thực tế</b>, không vượt quá phiếu — về sớm hơn thì
              trả theo thực tế.
            </span>
          </div>
          {/* DẢI SỐ DƯ TRẦN THÁNG — chỉ hiện khi công ty ĐÃ bật trần (`ap_tran`). Chưa bật thì
              đây là ô vô nghĩa, ẩn hẳn. Tổ trưởng tạo hộ: hiện sau khi chọn thợ. */}
          {tran?.ap_tran && conLai != null && (
            <div
              className={`tc-tran tc-tran--${
                conLai <= 0 ? "het" : conLai < TRAN_NGUONG_VANG ? "sap" : "con"
              }`}
            >
              <div className="tc-tran__row">
                <span className="tc-tran__thang">
                  Tháng {Number(thangKey.slice(5))}/{thangKey.slice(0, 4)}
                </span>
                <span className="tc-tran__dung">
                  Đã đăng ký <strong>{gioPhut(tran.da_dung_phut)}</strong> /{" "}
                  {gioPhut(tran.tran_phut)}
                </span>
                <span className="tc-tran__pill">Còn {gioPhut(conLai)}</span>
              </div>
              <span className="tc-tran__sub">
                Tính theo phiếu, kể cả phiếu chờ duyệt — không phải giờ đã bấm
                máy.
              </span>
            </div>
          )}
          <div className="ns-grid">
            {forEmployee && (
              <label className="ns-field">
                <span className="ns-field__label">Nhân viên *</span>
                <select
                  value={employeeId ?? ""}
                  onChange={(e) =>
                    setEmployeeId(
                      e.target.value ? Number(e.target.value) : null,
                    )
                  }
                >
                  <option value="">— chọn —</option>
                  {emps.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.full_name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label className="ns-field">
              <span className="ns-field__label">Ngày công *</span>
              <input
                type="date"
                value={workDate}
                onChange={(e) => setWorkDate(e.target.value)}
              />
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Từ giờ *</span>
              <input
                value={from}
                onChange={(e) => setFrom(e.target.value)}
                placeholder="22:00"
              />
            </label>
            <label className="ns-field">
              <span className="ns-field__label">Đến giờ *</span>
              <input
                value={to}
                onChange={(e) => setTo(e.target.value)}
                placeholder="03:00"
              />
            </label>
          </div>
          {/* Câu chặn nằm NGAY DƯỚI ô "Đến giờ" (chỗ phải sửa), nhưng chiếm trọn bề ngang: nhét
              vào ô 1/2 modal thì câu 2 dòng thành 6 dòng, đội cả lưới. */}
          {loiTran && <p className="tc-tran-err">{loiTran}</p>}
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">
              <input
                type="checkbox"
                checked={nextDay}
                onChange={(e) => setNextDay(e.target.checked)}
              />{" "}
              Giờ kết thúc rơi sang <b>hôm sau</b>
            </span>
            {minutes != null && minutes > 0 && (
              <span className="tc-muted">
                Tổng: {Math.floor(minutes / 60)}h
                {minutes % 60 ? ` ${minutes % 60}'` : ""} — ngày công{" "}
                {workDate ? fmtDateISO(workDate) : "…"}
              </span>
            )}
            {/* Cộng dồn cả tháng SAU KHI lưu phiếu này — cho thấy hậu quả trước khi bấm, thay vì
                để backend đá về. `da_dung_phut` đã trừ chính phiếu đang sửa (`exclude_id`). */}
            {tran?.ap_tran && minutes != null && minutes > 0 && (
              <span
                className={`tc-muted${
                  tran.da_dung_phut + minutes > tran.tran_phut
                    ? " tc-muted--vuot"
                    : ""
                }`}
              >
                ⇒ tháng này {gioPhut(tran.da_dung_phut + minutes)} /{" "}
                {gioPhut(tran.tran_phut)}
              </span>
            )}
          </label>
          <label className="ns-field" style={{ marginTop: 12 }}>
            <span className="ns-field__label">Lý do</span>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="vd: chạy đơn gấp cho khách"
            />
          </label>
        </div>
        <footer className="ns-modal__foot">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            Hủy
          </button>
          {/* Hành động chính của hộp thoại → cam (một nút cam mỗi hộp thoại).
              Vượt trần tháng ⇒ TẮT nút. Không có nhánh "gửi kèm lý do xin vượt". */}
          <Button
            variant="accent"
            onClick={save}
            loading={busy}
            disabled={vuotTran}
            title={loiTran ?? undefined}
          >
            {busy
              ? "Đang lưu…"
              : forEmployee
                ? "Tạo & duyệt luôn"
                : "Gửi phiếu"}
          </Button>
        </footer>
      </div>
    </div>
  );
}
